/* Run with the bundled Node runtime and PLAYWRIGHT_MODULE pointing at playwright.
   Requires an explicitly labeled demo_web.py process at HK_TEST_URL. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path');
let browser;
(async()=>{
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
 await page.addInitScript(()=>{
  const NativeResizeObserver=window.ResizeObserver;window.__activeChartObservers=0;
  window.ResizeObserver=class extends NativeResizeObserver{
   observe(...args){if(!this.counted){this.counted=true;window.__activeChartObservers++;}return super.observe(...args);}
   disconnect(){if(this.counted){this.counted=false;window.__activeChartObservers--;}return super.disconnect();}
  };
 });
 page.on('pageerror',e=>errors.push(e.message));
 const url=process.env.HK_TEST_URL||'http://127.0.0.1:18765';
 const output=process.env.HK_SCREENSHOT_DIR||'/tmp/hk-browser-smoke';fs.mkdirSync(output,{recursive:true});
 await page.goto(url);
 await page.getByText('OFFLINE SCRIPTED DEMO / No LLM is connected.',{exact:false}).waitFor();
 await page.getByRole('button',{name:'Tencent overview + chart'}).click();
 await page.getByRole('button',{name:'Send / 发送',exact:true}).click();
 await page.locator('.chart svg').first().waitFor({timeout:30000});
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='');
 if(await page.locator('.chart svg').count()!==2)throw Error('Expected price and volatility charts');
 await page.getByText('Timing details / 耗时详情',{exact:true}).first().click();
 await page.getByText('Model API / 模型请求',{exact:true}).first().waitFor();
 if(await page.evaluate(()=>window.__activeChartObservers)!==2)throw Error('Chart observers leaked after render');
 await page.screenshot({path:path.join(output,'desktop-overview.png'),fullPage:true});
 await page.reload();
 await page.locator('.chart svg').first().waitFor();
 await page.getByRole('button',{name:'＋ New conversation / 新对话',exact:true}).click();
 if(await page.evaluate(()=>window.__activeChartObservers)!==0)throw Error('Detached chart observers were not disconnected');
 await page.getByRole('button',{name:'Screen profitable, low-debt companies'}).click();
 await page.getByRole('button',{name:'Send / 发送',exact:true}).click();
 await page.getByText('Eligible companies:',{exact:false}).waitFor({timeout:30000});
 await page.locator('#question').fill('Keep the same criteria and show the top 10.');
 await page.getByRole('button',{name:'Send / 发送',exact:true}).click();
 await page.locator('.turn').nth(1).locator('.evidence').first().waitFor({timeout:30000});
 if(!await page.locator('.turn').nth(1).innerText().then(t=>t.includes('"top_k":10')))throw Error('Ranking follow-up lost Top-K');
 await page.screenshot({path:path.join(output,'desktop-ranking.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:path.join(output,'mobile-ranking.png'),fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Mobile page overflows horizontally');
 await page.locator('#sessions .session').filter({hasText:"Show Tencent"}).click();
 await page.locator('.chart svg').first().waitFor();
 await page.screenshot({path:path.join(output,'mobile-overview.png'),fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Mobile chart page overflows');
 await page.getByRole('button',{name:'＋ New conversation / 新对话',exact:true}).click();
 await page.locator('#question').fill('<img src=x onerror="window.injected=true">');
 await page.getByRole('button',{name:'Send / 发送',exact:true}).click();
 await page.locator('.answer').waitFor({timeout:30000});
 if(await page.evaluate(()=>!!window.injected))throw Error('Unsafe HTML rendering');
 if(await page.locator('#sessions .session').count()!==3)throw Error('Missing conversation entries');
 if(errors.length)throw Error(errors.join('\n'));
 fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({passed:true,scripted:true,checks:['overview tables','price and volatility charts','timing breakdown','chart observer cleanup','browser reload','new conversation','ranking and Top-K follow-up','mobile overflow','HTML escaped','no JS errors']},null,2));
 await browser.close();console.log('Browser smoke checks passed. Screenshots: '+output);
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exit(1)});
