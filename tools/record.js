// Renders each emotion scene to a short mp4 using Playwright + ffmpeg.
const {chromium}=require('playwright');const {execSync}=require('child_process');const fs=require('fs'),path=require('path');
const ids=['joy','love','laugh','sad','angry','surprised','scared','sleepy','think','blush','cool','hello'];
const out=process.argv[2], tmp=fs.mkdtempSync('/tmp/chiprec-');
(async()=>{const b=await chromium.launch();
for(const id of ids){
  const ctx=await b.newContext({viewport:{width:480,height:480},recordVideo:{dir:tmp+'/'+id,size:{width:480,height:480}}});
  const p=await ctx.newPage();
  await p.goto('file://'+path.resolve(__dirname,'render.html')+'#'+id);
  await p.waitForTimeout(5200);
  await ctx.close();
  const f=fs.readdirSync(tmp+'/'+id)[0];
  execSync(`ffmpeg -y -loglevel error -ss 1.0 -t 4 -i ${tmp}/${id}/${f} -vf "scale=360:360,fps=30" -an -c:v libx264 -profile:v main -pix_fmt yuv420p -crf 26 -movflags +faststart ${out}/clip_${id}.mp4`);
  console.log('ok',id);
}
await b.close();})();
