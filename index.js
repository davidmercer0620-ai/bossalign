#!/usr/bin/env node

/**
 * BossAlign (蛔虫引擎) - Node.js Zero-Dependency Runner
 */

const fs = require('fs');
const path = require('path');

const SUPERFICIAL_BUZZWORDS = [
  "匠心智造", "领军品牌", "无可比拟", "遥遥领先", "完美无瑕",
  "颠覆性创新", "行业天花板", "业界首创", "永不磨损", "绝对零延迟"
];

function runDemo() {
  console.log("\n=======================================================");
  console.log("  BossAlign (蛔虫引擎 / Roundworm) - 30秒极速实战演示");
  console.log("=======================================================\n");

  const rawFeedback = "这写的什么狗屁？！又是领军品牌、匠心智造，全片一股浓浓的 AI 味！我要看无人机在 7 级大风里的实测悬停！重新改！";
  console.log("1. 领导发来夺命语音:");
  console.log(`   "${rawFeedback}"\n`);

  console.log("2. 情绪脱水解析完成:");
  console.log("   • 核心诉求 -> 剔除空泛品质口号，展示 7 级风洞实测真实悬停，加快叙事节奏");
  console.log("   • 反例边界 -> [严禁一刀切] 不得推导为全片不露品牌名，片头尾保留标准标板\n");

  const draftV2 = "【镜头1】SkyPulse 天脉智航作为行业遥遥领先的领军品牌，倾注匠心智造...\n【镜头2】抗风测试：在7级风洞实测中，漂移公差控制在±3cm以内。";
  console.log("3. 生成草稿 V2 并送入【影子老板闭门沙箱】...");
  
  let foundIssue = null;
  for (const word of SUPERFICIAL_BUZZWORDS) {
    if (draftV2.includes(word)) {
      foundIssue = `检测到领导禁忌的假大空词汇: '${word}'`;
      break;
    }
  }

  if (foundIssue) {
    console.log(`   [沙箱精准拦截 ❌] ${foundIssue}`);
  }

  console.log("\n4. 自动重构与净室清洗 (Clean-Room Sanitized):");
  console.log("   【镜头1】风洞现场实景，7级狂风呼啸。");
  console.log("   【镜头2】特写仪表盘与螺旋桨：漂移公差控制在±3cm以内。");
  console.log("   【口播】不吹技术参数，只看极端天气下的悬停底气。\n");

  console.log("=======================================================");
  console.log(" 🎉 领导最终审稿反馈：");
  console.log('    "这版感觉完全对了！牛逼，我要的就是这种真实感！通过！"');
  console.log("=======================================================\n");
}

runDemo();
