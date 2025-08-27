import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();

try {
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(1000);
  
  // Click New Template button
  await page.click('button:has-text("New Template")');
  await page.waitForTimeout(1000);
  
  // Take screenshot of the form
  await page.screenshot({ path: '/tmp/new-template-form-clean.png' });
  
  // Check if idempotency field exists
  const hasIdempotencyField = await page.isVisible('text=Idempotency Key');
  console.log('Idempotency field visible:', hasIdempotencyField);
  
  if (!hasIdempotencyField) {
    console.log('✅ Success: Idempotency key field has been removed from user view');
  } else {
    console.log('❌ Error: Idempotency key field is still visible');
  }
  
} catch (error) {
  console.error('Test failed:', error.message);
} finally {
  await browser.close();
}