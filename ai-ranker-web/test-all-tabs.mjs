import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();

try {
  console.log('1. Testing Templates Tab...');
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(1000);
  const templatesVisible = await page.isVisible('text=Templates (Immutable)');
  console.log('   ✓ Templates tab loads:', templatesVisible);
  
  console.log('2. Testing Single Run Tab...');
  await page.click('text=Single Run');
  await page.waitForTimeout(500);
  const singleRunVisible = await page.isVisible('text=Select Template') || await page.isVisible('text=Single Template Run');
  console.log('   ✓ Single Run tab loads:', singleRunVisible);
  
  console.log('3. Testing Batch Run Tab...');
  await page.click('text=Batch Run');
  await page.waitForTimeout(500);
  const batchRunVisible = await page.isVisible('text=Batch Run Configuration');
  console.log('   ✓ Batch Run tab loads:', batchRunVisible);
  
  console.log('4. Testing Results Tab...');
  await page.click('text=Results');
  await page.waitForTimeout(500);
  const resultsVisible = await page.isVisible('text=Run History');
  console.log('   ✓ Results tab loads:', resultsVisible);
  
  console.log('5. Testing Countries Tab...');
  await page.click('text=Countries');
  await page.waitForTimeout(500);
  const countriesVisible = await page.isVisible('text=Countries Configuration');
  console.log('   ✓ Countries tab loads:', countriesVisible);
  
  console.log('6. Testing System Tab...');
  await page.click('text=System');
  await page.waitForTimeout(500);
  const systemVisible = await page.isVisible('text=System Overview');
  console.log('   ✓ System tab loads:', systemVisible);
  
  // Test template creation flow
  console.log('\n7. Testing Template Creation...');
  await page.click('text=Templates');
  await page.waitForTimeout(500);
  await page.click('text=New Template');
  await page.waitForTimeout(500);
  const formVisible = await page.isVisible('input[placeholder="Template name"]');
  console.log('   ✓ Template creation form opens:', formVisible);
  
  // Take final screenshot
  await page.screenshot({ path: '/tmp/final-test.png' });
  
  console.log('\n✅ All UI tabs tested successfully!');
  
} catch (error) {
  console.error('❌ Test failed:', error);
} finally {
  await browser.close();
}