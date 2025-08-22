"""
Background task runner that bypasses HTTP context to fix DE leak.
Uses threading to run prompts outside of FastAPI's request context.
"""

import asyncio
import threading
import uuid
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import text
import json
import time

from app.database import engine
from app.llm.langchain_adapter import LangChainAdapter
from app.services.als import als_service
from app.services.als.country_codes import country_to_num
from app.cache.upstash_cache import cache


class BackgroundTaskRunner:
    """Runs prompt tasks in background threads to bypass HTTP context"""
    
    def __init__(self):
        self.tasks = {}  # Store task status in memory
        self.lock = threading.Lock()
    
    def submit_task(
        self,
        run_id: int,
        template_id: int,
        brand_name: str,
        model_name: str,
        country_iso: str,
        grounding_mode: str,
        prompt_text: str
    ) -> str:
        """Submit a task to run in the background"""
        
        task_id = str(uuid.uuid4())
        
        # Store initial task status
        with self.lock:
            self.tasks[task_id] = {
                'status': 'pending',
                'run_id': run_id,
                'started_at': datetime.utcnow().isoformat(),
                'result': None,
                'error': None
            }
        
        # Start background thread
        thread = threading.Thread(
            target=self._run_task_in_thread,
            args=(task_id, run_id, template_id, brand_name, model_name, 
                  country_iso, grounding_mode, prompt_text),
            daemon=True
        )
        thread.start()
        
        return task_id
    
    def _run_task_in_thread(
        self,
        task_id: str,
        run_id: int,
        template_id: int,
        brand_name: str,
        model_name: str,
        country_iso: str,
        grounding_mode: str,
        prompt_text: str
    ):
        """Run task in separate thread with new event loop"""
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Update status to running
            with self.lock:
                self.tasks[task_id]['status'] = 'running'
            
            # Run the async task
            result = loop.run_until_complete(
                self._execute_prompt_async(
                    run_id, template_id, brand_name, model_name,
                    country_iso, grounding_mode, prompt_text
                )
            )
            
            # Update task with result
            with self.lock:
                self.tasks[task_id]['status'] = 'completed'
                self.tasks[task_id]['result'] = result
                self.tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
            
            # Also store in cache for persistence  
            # Use the existing loop instead of creating a new one
            loop.run_until_complete(cache.set(f"task:{task_id}", {
                'status': 'completed',
                'result': result
            }, ttl=3600))
            
        except Exception as e:
            # Update task with error
            with self.lock:
                self.tasks[task_id]['status'] = 'failed'
                self.tasks[task_id]['error'] = str(e)
                self.tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
            
            # Store error in cache
            # Use the existing loop instead of creating a new one
            loop.run_until_complete(cache.set(f"task:{task_id}", {
                'status': 'failed',
                'error': str(e)
            }, ttl=3600))
            
        finally:
            loop.close()
    
    async def _execute_prompt_async(
        self,
        run_id: int,
        template_id: int,
        brand_name: str,
        model_name: str,
        country_iso: str,
        grounding_mode: str,
        prompt_text: str
    ) -> Dict[str, Any]:
        """Execute the prompt outside HTTP context"""
        
        print(f"\n{'='*60}")
        print(f"BACKGROUND TASK - EXECUTING PROMPT")
        print(f"Thread: {threading.current_thread().name}")
        print(f"Run ID: {run_id}")
        print(f"Country: {country_iso}")
        print(f"{'='*60}\n")
        
        try:
            # Convert country code to numeric to prevent leaks
            country_num = country_to_num(country_iso)
            
            # Create NEW adapter instance for complete isolation
            adapter = LangChainAdapter()
            
            # Build Ambient Block
            ambient_block = ""
            if country_num != 0:
                if country_iso in ['DE', 'CH', 'US', 'GB', 'AE', 'SG', 'IT', 'FR']:
                    try:
                        ambient_block = als_service.build_als_block(country_iso)
                    except Exception as e:
                        print(f"Failed to build Ambient Block: {e}")
            
            # Prepare prompt
            if country_num == 0:  # NONE
                if grounding_mode == "web":
                    full_prompt = f"Please use web search to answer this question accurately:\n\n{prompt_text}"
                else:
                    full_prompt = f"Based only on your training data (do not search the web):\n\n{prompt_text}"
                context_message = None
            else:
                if ambient_block:
                    full_prompt = prompt_text  # NAKED prompt
                    context_message = ambient_block
                else:
                    if grounding_mode == "web":
                        full_prompt = f"Please use web search to answer this question accurately:\n\n{prompt_text}"
                    else:
                        full_prompt = f"Based only on your training data (do not search the web):\n\n{prompt_text}"
                    context_message = None
            
            # Fixed parameters
            temperature = 0.0
            seed = 42
            
            # Get model response
            if model_name in ["gemini", "gemini-flash"]:
                response_data = await adapter.analyze_with_gemini(
                    full_prompt,
                    grounding_mode == "web",
                    model_name="gemini-2.0-flash-exp" if model_name == "gemini-flash" else "gemini-2.5-pro",
                    temperature=temperature,
                    seed=seed,
                    context=context_message
                )
            else:
                response_data = await adapter.analyze_with_gpt4(
                    full_prompt,
                    model_name=model_name,
                    temperature=temperature,
                    seed=seed,
                    context=context_message
                )
            
            # Extract response
            response = response_data.get("content", "") if isinstance(response_data, dict) else str(response_data) if response_data else ""
            
            # Check for leaks
            leak_detected = False
            leak_terms = []
            
            if response and 'DE' in response:
                leak_detected = True
                leak_terms.append('DE')
                print(f"[BACKGROUND] Leak detected: DE found in response")
            
            if response and 'Germany' in response:
                leak_detected = True
                leak_terms.append('Germany')
                print(f"[BACKGROUND] Leak detected: Germany found in response")
            
            if response and 'Deutschland' in response:
                leak_detected = True
                leak_terms.append('Deutschland')
            
            if response and 'location context' in response.lower():
                leak_detected = True
                leak_terms.append('location context')
                print(f"[BACKGROUND] Leak detected: 'location context' found")
            
            # Analyze response
            brand_mentioned = brand_name.lower() in response.lower()
            mention_count = response.lower().count(brand_name.lower())
            
            # Save to database (simplified schema)
            with engine.begin() as conn:
                result_query = text("""
                    INSERT INTO prompt_results 
                    (run_id, prompt_text, model_response, brand_mentioned, mention_count, 
                     competitors_mentioned, confidence_score)
                    VALUES (:run_id, :prompt, :response, :mentioned, :count, 
                            :competitors, :confidence)
                """)
                
                conn.execute(result_query, {
                    "run_id": run_id,
                    "prompt": full_prompt,
                    "response": response,
                    "mentioned": brand_mentioned,
                    "count": mention_count,
                    "competitors": json.dumps([]),
                    "confidence": 0.8 if brand_mentioned else 0.3
                })
                
                # Update run status
                update_query = text("""
                    UPDATE prompt_runs 
                    SET status = 'completed', completed_at = datetime('now')
                    WHERE id = :id
                """)
                conn.execute(update_query, {"id": run_id})
            
            print(f"\n[BACKGROUND] Task completed. Leak detected: {leak_detected}")
            if leak_detected:
                print(f"[BACKGROUND] Leak terms: {', '.join(leak_terms)}")
            
            return {
                "run_id": run_id,
                "country": country_iso,
                "grounding_mode": grounding_mode,
                "brand_mentioned": brand_mentioned,
                "mention_count": mention_count,
                "response_preview": response[:200] + "..." if len(response) > 200 else response,
                "status": "completed",
                "leak_detected": leak_detected,
                "leak_terms": leak_terms
            }
            
        except Exception as e:
            print(f"[BACKGROUND] Error: {e}")
            
            # Update database with error
            with engine.begin() as conn:
                error_query = text("""
                    UPDATE prompt_runs 
                    SET status = 'failed', error_message = :error, completed_at = datetime('now')
                    WHERE id = :id
                """)
                conn.execute(error_query, {"id": run_id, "error": str(e)})
            
            raise
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a task"""
        
        # Check memory first
        with self.lock:
            if task_id in self.tasks:
                return self.tasks[task_id].copy()
        
        # Skip cache check for now - was causing async errors
        # TODO: Make this method async or use sync cache client
        
        return {'status': 'not_found', 'error': 'Task not found'}
    
    def get_all_tasks(self) -> Dict[str, Any]:
        """Get status of all tasks"""
        with self.lock:
            return self.tasks.copy()


# Global instance
background_runner = BackgroundTaskRunner()