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
 let r=await ask('Fetch AAPL historical prices online and show a price and moving-average chart using a 60-return window.');
 const first=r.evidence?.find(e=>e.tool==='market_history'&&!e.reused);
 if(!first||first.arguments.window!==60||first.symbol!=='AAPL'||first.chart?.dates?.length!==61)throw Error('Missing external AAPL chart/window');
 r=await ask('For the same stock, use a 120-return price window and show the historical chart again.');
 if(!r.evidence?.some(e=>e.tool==='market_history'&&!e.reused&&e.arguments.window===120&&e.symbol==='AAPL'&&e.chart?.dates?.length===121))throw Error('External follow-up did not retain AAPL and update its window');
 r=await ask('Read https://www.microsoft.com/en-us/Investor/ and briefly describe this official page, citing the retrieved evidence.');
 if(!r.evidence?.some(e=>e.tool==='read_webpage'&&!e.reused&&e.sources?.length))throw Error('Missing retrieved primary-page sources');
 r=await ask('Check online the claim that Anthropic has recently IPOed. Verify the exact company and listing status using current sources, including an official company page if accessible. Do not accept the premise or invent a ticker. Clearly state what remains uncertain.');
 if(!r.evidence?.some(e=>['web_search','read_webpage','search_stocks'].includes(e.tool)&&!e.reused))throw Error('Anthropic query did not retrieve outside-universe evidence');
 if(/not (?:part of|in) (?:the )?(?:fixed|supported).*thirty|outside (?:the )?supported universe/i.test(r.explanation||''))throw Error('Anthropic was refused due to the old universe restriction');
 if(replies.some(r=>r.fallback))throw Error('Unexpected explanation fallback in live browser turns');
 await page.locator('.chart svg').first().waitFor();
 await page.screenshot({path:path.join(output,'real-server-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'real-server-mobile.png'),fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error('Mobile page overflows');
 if(errors.length)throw Error(errors.join('\n'));
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,scripted:false,turns:replies,checks:['real server route','external AAPL history','contextual window change 60 to 120','primary page and source links','Anthropic listing claim checked online','desktop and mobile','no JS errors','no fallback']},null,2));
 console.log('Online server browser checks passed: '+output);await browser.close();
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exit(1)});
