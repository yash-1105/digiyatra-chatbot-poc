// Presentation regressions only. No chat submissions, credentials or production writes.
import { chromium } from 'playwright-core';
import { mkdirSync, writeFileSync } from 'node:fs';
const BASE=process.env.BASE_URL??'http://127.0.0.1:3000';
const OUT=process.env.SCREENSHOT_DIR??new URL('../screenshots/redesign/',import.meta.url).pathname;
mkdirSync(OUT,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH});
const checks=[];const errors=[];
const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)errors.push(name);};
try {
 for(const [device,width,height] of [['desktop',1440,1000],['laptop',1366,768],['tablet',820,1180],['mobile',390,844]]) {
  const ctx=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
  const p=await ctx.newPage();p.on('pageerror',e=>errors.push(device+': '+e.message));
  const home=await p.goto(BASE,{waitUntil:'networkidle'});await p.evaluate(()=>document.fonts.ready);
  check(device+' public homepage',home.status()===200&&!home.headers()['www-authenticate']);
  check(device+' new hero and dark identity',await p.locator('.foundation-hero').evaluate(el=>getComputedStyle(el).backgroundColor==='rgb(21, 13, 47)'));
  check(device+' no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  check(device+' all existing information anchors',await p.evaluate(()=>['about','how-it-works','registration','journey','airports','privacy','faq','support','whats-new','welcome'].every(id=>document.getElementById(id))));
  check(device+' independent identity visible',await p.getByText('Independent information portal',{exact:true}).isVisible());
  check(device+' disclaimer retained',await p.locator('footer').innerText().then(t=>t.includes('not an official website')));
  check(device+' reduced motion honored',await p.locator('.hero-light-trail i').first().evaluate(el=>parseFloat(getComputedStyle(el).animationDuration)<.1));
  const nav=p.getByRole('button',{name:'Menu',exact:true});
  if(await nav.isVisible()){
   await nav.click();check(device+' mobile navigation expands',await p.locator('#mobile-nav').isVisible());
   await p.keyboard.press('Escape');check(device+' menu keyboard close',await nav.getAttribute('aria-expanded')==='false');
  }
  if(['desktop','mobile'].includes(device)){
   await p.screenshot({path:OUT+'/'+device+'-home.png'});
   await p.screenshot({path:OUT+'/'+device+'-full.png',fullPage:true});
   await p.locator('#about').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));await p.screenshot({path:OUT+'/'+device+'-about.png'});
   await p.locator('#registration').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));await p.screenshot({path:OUT+'/'+device+'-registration.png'});
  }
  const storeLinks=await p.locator('#registration a[href*="play.google.com"],#registration a[href*="apps.apple.com"]').count();check(device+' both official app links retained',storeLinks===2);
  await p.locator('#airport-search').fill('BLR');check(device+' airport search works',await p.locator('#airports').innerText().then(t=>t.includes('Kempegowda')));await p.locator('#airport-search').fill('');
  await p.locator('#faq-search').fill('boarding');check(device+' FAQ search works',await p.locator('#faq [aria-live="polite"]').innerText().then(t=>t.includes('result')));await p.locator('#faq-search').fill('');
  await p.getByRole('button',{name:'Open Digi Yatra Assistant'}).click();
  const dialog=p.getByRole('dialog',{name:'Digi Yatra Assistant'});
  await dialog.evaluate(async el=>{await Promise.all(el.getAnimations().map(a=>a.finished));});
  check(device+' chat fits viewport',await dialog.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1&&r.top>=-1&&r.bottom<=innerHeight+1;}));
  await p.getByRole('combobox',{name:'Response language'}).selectOption('hi');
  await p.getByRole('combobox',{name:'AI provider'}).selectOption('anthropic');
  check(device+' Hindi chat controls',await p.getByRole('button',{name:'संदेश भेजें',exact:true}).count()===1);
  if(['desktop','mobile'].includes(device))await p.screenshot({path:OUT+'/'+device+'-chat.png'});
  await p.keyboard.press('Escape');await p.reload({waitUntil:'networkidle'});await p.getByRole('button',{name:'डिजी यात्रा सहायक खोलें'}).click();
  check(device+' provider and language persist',await p.getByRole('combobox',{name:'Response language'}).inputValue()==='hi'&&await p.getByRole('combobox',{name:'AI provider'}).inputValue()==='anthropic');
  await p.keyboard.press('Escape');await p.getByRole('button',{name:'High contrast',exact:true}).click();
  check(device+' high contrast applies',await p.locator('html').getAttribute('data-contrast')==='high');
  if(device==='mobile')await p.screenshot({path:OUT+'/mobile-high-contrast.png'});
  await p.getByRole('button',{name:'Standard contrast',exact:true}).click();
  await p.getByRole('button',{name:'Increase text size',exact:true}).click();
  check(device+' enlarged text no page overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await p.goto(BASE+'/admin/login',{waitUntil:'networkidle'});check(device+' login form retained',await p.getByRole('heading',{name:'Administrator Login',exact:true}).isVisible());
  await p.getByRole('button',{name:'Login',exact:true}).click();check(device+' login validation retained',await p.getByText('Enter your email address.',{exact:true}).isVisible());
  check(device+' admin login no overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  if(['desktop','mobile'].includes(device))await p.screenshot({path:OUT+'/'+device+'-login.png'});
  await p.goto(BASE+'/admin/dashboard',{waitUntil:'networkidle'});check(device+' admin protection retained',p.url().includes('/admin/login'));
  await ctx.close();
 }
}finally{await browser.close();writeFileSync(OUT+'/results.json',JSON.stringify({checks,errors},null,2));}
console.log(JSON.stringify({passed:checks.filter(c=>c.ok).length,total:checks.length,errors,screenshots:OUT}));
if(errors.length)process.exitCode=1;
