import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();

// Listen for console messages
page.on('console', msg => {
  if (msg.type() === 'error') {
    console.log('❌ Console Error:', msg.text());
  }
});

// Listen for page errors
page.on('pageerror', error => {
  console.log('❌ Page Error:', error.message);
});

try {
  console.log('Testing all tabs and checking for errors...\n');
  
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(2000);
  
  const tabs = [
    { name: 'Templates', selector: 'text=Templates (Immutable)' },
    { name: 'Single Run', selector: 'text=Single Template Run' },
    { name: 'Batch Run', selector: 'text=Batch Run Configuration' },
    { name: 'Results', selector: 'text=Run History' },
    { name: 'Countries', selector: 'text=Countries Configuration' },
    { name: 'System', selector: 'text=System Overview' }
  ];
  
  for (const tab of tabs) {
    console.log(`Testing ${tab.name} tab...`);
    
    // Click tab button
    await page.click(`button:has-text("${tab.name.split(' ')[0]}")`);
    await page.waitForTimeout(1000);
    
    // Check if content loads
    try {
      const visible = await page.isVisible(tab.selector, { timeout: 2000 });
      console.log(`  ✓ ${tab.name} content visible:`, visible);
    } catch (e) {
      console.log(`  ❌ ${tab.name} content not found`);
    }
    
    // Take screenshot
    await page.screenshot({ path: `/tmp/tab-${tab.name.replace(' ', '-').toLowerCase()}.png` });
  }
  
  console.log('\n✅ Testing complete!');
  
} catch (error) {
  console.error('❌ Test failed:', error.message);
} finally {
  await browser.close();
}