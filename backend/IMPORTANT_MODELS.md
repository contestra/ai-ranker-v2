# IMPORTANT: ONLY TWO MODELS ARE USED IN THIS PROJECT

## DO NOT USE ANY OTHER MODEL NAMES

### OpenAI
- **Model Name**: `gpt-5`
- **Max Tokens**: Always use `6000` (or None to use default of 6000)
- **Minimum**: Never use less than 16 tokens (API minimum)
- **Testing**: ALWAYS use `max_tokens=6000` or omit it entirely
- **NOT**: gpt-4, gpt-4o, gpt-3.5, gpt-4-turbo, etc.

### Vertex AI (Google)  
- **Model Name**: `gemini-2.5-pro`
- **Max Tokens**: Use appropriate values or None for default
- **NOT**: gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp, gemini-pro, etc.

## Testing Requirements
- **NEVER** use `max_tokens` less than 6000 for testing
- Either set `max_tokens=6000` or omit it to use the default
- The OpenAI API has a minimum of 16 tokens
- Our default is 6000 tokens (set in .env)

## Summary
- **OpenAI**: `gpt-5` ONLY with `max_tokens=6000`
- **Vertex**: `gemini-2.5-pro` ONLY

Any reference to other models is an error and should be corrected immediately.

Last Updated: 2025-08-26