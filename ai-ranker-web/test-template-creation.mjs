import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

try {
  console.log('🧪 Testing Template Creation and Execution\n');
  
  // 1. Navigate to the app
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(2000);
  
  // 2. Click New Template button
  console.log('1. Creating new template...');
  await page.click('button:has-text("New Template")');
  await page.waitForTimeout(1000);
  
  // 3. Fill in template form
  console.log('2. Filling template form...');
  
  // Template name
  await page.fill('input[placeholder="Template name"]', 'Test Template GPT5');
  
  // Select adapter (should already be openai)
  await page.click('button[role="combobox"]:has-text("openai")');
  await page.waitForTimeout(500);
  
  // Select model - click the model dropdown
  const modelSelectors = await page.$$('button[role="combobox"]');
  if (modelSelectors.length > 1) {
    await modelSelectors[1].click();
    await page.waitForTimeout(500);
    await page.click('div[role="option"]:has-text("gpt-5")');
  }
  
  // Fill system prompt
  const textareas = await page.$$('textarea');
  if (textareas.length > 0) {
    await textareas[0].fill('You are a helpful assistant.');
  }
  
  // Fill query template
  if (textareas.length > 1) {
    await textareas[1].fill('Say hello in a friendly way.');
  }
  
  await page.screenshot({ path: '/tmp/template-form-filled.png' });
  
  // 4. Save template
  console.log('3. Saving template...');
  await page.click('button:has-text("Save")');
  await page.waitForTimeout(2000);
  
  // 5. Navigate to Single Run tab
  console.log('4. Testing template execution...');
  await page.click('button:has-text("Single Run")');
  await page.waitForTimeout(1000);
  
  // 6. Select the template we just created
  await page.click('button[role="combobox"]');
  await page.waitForTimeout(500);
  const hasTestTemplate = await page.isVisible('text=Test Template GPT5');
  console.log('   ✓ Template appears in dropdown:', hasTestTemplate);
  
  if (hasTestTemplate) {
    await page.click('text=Test Template GPT5');
    await page.waitForTimeout(500);
  }
  
  // 7. Run the template
  await page.click('button:has-text("Run Template")');
  await page.waitForTimeout(2000);
  
  await page.screenshot({ path: '/tmp/template-run-result.png' });
  
  // 8. Check Results tab
  console.log('5. Checking Results tab...');
  await page.click('button:has-text("Results")');
  await page.waitForTimeout(1000);
  
  const hasResults = await page.isVisible('text=Run History');
  console.log('   ✓ Results tab shows history:', hasResults);
  
  await page.screenshot({ path: '/tmp/results-final.png' });
  
  console.log('\n✅ Template creation and execution test complete!');
  console.log('   Screenshots saved to /tmp/');
  
} catch (error) {
  console.error('❌ Test failed:', error.message);
  await page.screenshot({ path: '/tmp/error-screenshot.png' });
} finally {
  await browser.close();
}