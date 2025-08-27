import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();

try {
  console.log('🔍 Testing System Prompt Removal (CRITICAL BUG FIX)\n');
  
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(1000);
  
  // Click New Template button
  await page.click('button:has-text("New Template")');
  await page.waitForTimeout(1000);
  
  // Take screenshot of the form
  await page.screenshot({ path: '/tmp/no-system-prompt-field.png' });
  
  // Check if system prompt field exists
  const hasSystemPromptField = await page.isVisible('text=System Prompt');
  const hasSystemPromptTextarea = await page.isVisible('textarea#system_prompt');
  
  console.log('System Prompt label visible:', hasSystemPromptField);
  console.log('System Prompt textarea visible:', hasSystemPromptTextarea);
  
  if (!hasSystemPromptField && !hasSystemPromptTextarea) {
    console.log('\n✅ SUCCESS: System Prompt field has been removed');
    console.log('   - ALS system prompt integrity is now protected');
    console.log('   - Backend will inject appropriate prompts');
    console.log('   - User cannot break ALS calibration');
  } else {
    console.log('\n❌ CRITICAL: System Prompt field is still visible!');
    console.log('   - This will break ALS locale inference');
    console.log('   - Must be removed immediately');
  }
  
  // Verify Query Template is still there
  const hasQueryTemplate = await page.isVisible('text=Query Template');
  console.log('\nQuery Template field (should exist):', hasQueryTemplate);
  
} catch (error) {
  console.error('Test failed:', error.message);
} finally {
  await browser.close();
}