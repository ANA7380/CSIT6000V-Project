/* Real TACC browser verification. Start scripts/tacc.py bridge JOB_ID first.
   This DOES call the model through your already-running server job. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path');
let browser;
(async()=>{
 const target=process.env.HK_TEST_URL||'http://127.0.0.1:18775';
 const output=process.env.HK_SCREENSHOT_DIR||'/tmp/hk-server-browser';fs.mkdirSync(output,{recursive:true});
 browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],replies=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(target);
 await page.getByRole('heading',{name:'Research with evidence'}).waitFor();
 if(await page.getByText('OFFLINE SCRIPTED DEMO',{exact:false}).count())throw Error('Expected real server, got scripted demo');
 async function ask(question){await page.locator('#question').fill(question);const completed=page.waitForResponse(r=>r.url().includes('/reply/')&&r.status()===200,{timeout:600000});await page.getByRole('button',{name:'Send / 发送',exact:true}).click();const r=await(await completed).json();await page.waitForFunction(()=>!document.querySelector('form button').disabled,{timeout:600000});replies.push(r);if(r.error)throw Error(r.error);return r;}
 let r=await ask('Show all four financial metrics for 0700.HK using 60 daily returns for volatility.');
 const first=r.evidence?.find(e=>e.tool==='ticker_metrics'&&!e.reused);
 if(!first||first.arguments.window!==60)throw Error('Missing live core-metrics tool/window');
 r=await ask('For the same stock, use 120 daily returns for historical volatility.');
 if(!r.evidence?.some(e=>e.tool==='ticker_metrics'&&!e.reused&&e.arguments.window===120&&e.symbol==='0700.HK'))throw Error('Live follow-up did not retain ticker and update window');
 r=await ask('Show a historical price and moving-average chart for that same stock, using a 60-return window. Do not predict future prices.');
 if(!r.evidence?.some(e=>e.tool==='price_analysis'&&!e.reused&&e.chart?.dates?.length===61))throw Error('Missing verified live chart series');
 if(replies.some(r=>r.fallback))throw Error('Unexpected explanation fallback in live browser turns');
 await page.locator('.chart svg').first().waitFor();
 await page.screenshot({path:path.join(output,'real-server-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'real-server-mobile.png'),fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Mobile page overflows');
 if(errors.length)throw Error(errors.join('\n'));
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,scripted:false,turns:replies,checks:['real server route','live metrics','contextual window change','historical chart','desktop and mobile','no JS errors']},null,2));
 console.log('Real server browser checks passed: '+output);await browser.close();
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exit(1)});
