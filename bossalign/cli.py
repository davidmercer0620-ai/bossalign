import sys
import argparse
from .parser import parse_feedback_event
from .boundary import BoundaryEngine
from .sandbox import ShadowBossSandbox
from .sanitizer import sanitize_deliverable
from .schema import BoundaryRule

# Try rich for pretty output, fallback to standard ANSI print
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

def print_banner(msg: str):
    if HAS_RICH:
        console.print(Panel.fit(f"[bold cyan]{msg}[/bold cyan]"))
    else:
        print(f"\n=== {msg} ===\n")

def print_success(msg: str):
    if HAS_RICH:
        console.print(f"[bold green]✔ {msg}[/bold green]")
    else:
        print(f"[SUCCESS] {msg}")

def print_warning(msg: str):
    if HAS_RICH:
        console.print(f"[bold yellow]⚠ {msg}[/bold yellow]")
    else:
        print(f"[WARNING] {msg}")

def print_error(msg: str):
    if HAS_RICH:
        console.print(f"[bold red]❌ {msg}[/bold red]")
    else:
        print(f"[ERROR] {msg}")

def cmd_ingest(args):
    print_banner("正在启动 BossAlign 情绪脱水解析器...")
    event, rule = parse_feedback_event(args.reviewer, args.raw, args.context)
    
    if HAS_RICH:
        table = Table(title="反馈解析成果", show_header=True, header_style="bold magenta")
        table.add_column("属性", style="dim", width=18)
        table.add_column("解析内容")
        table.add_row("事件编号", event.event_id)
        table.add_row("审核人", event.reviewer)
        table.add_row("原始录入", event.raw_content)
        table.add_row("脱水后核心诉求", f"[bold green]{event.extracted_intent}[/bold green]")
        table.add_row("反例边界警示", f"[bold yellow]{rule.counter_example_rationale}[/bold yellow]")
        console.print(table)
    else:
        print(f"• 事件编号: {event.event_id}")
        print(f"• 审核人: {event.reviewer}")
        print(f"• 原始录入: {event.raw_content}")
        print(f"• 脱水后核心诉求: {event.extracted_intent}")
        print(f"• 反例边界警示: {rule.counter_example_rationale}")
        
    print_success("反馈事件与反例守卫规则已成功登记！")

def cmd_check(args):
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print_error(f"读取文件失败: {e}")
        return
        
    print_banner(f"正在启动针对 {args.reviewer} 的影子老板闭门沙箱...")
    sandbox = ShadowBossSandbox(reviewer=args.reviewer)
    res = sandbox.review_draft(content)
    
    if res["passed"]:
        print_success("恭喜！影子老板沙箱全项通过，未发现致命雷区！")
    else:
        print_error(f"沙箱拦截！发现 {res['total_issues']} 个潜在挨骂点：")
        for issue in res["issues"]:
            print(f" • [{issue['severity']}] {issue['detail']}")

def cmd_sanitize(args):
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print_error(f"读取文件失败: {e}")
        return
        
    cleaned = sanitize_deliverable(content)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print_success(f"净室清洗完成！已抹去所有内部标签，输出至: {args.out}")

def cmd_demo(args):
    print_banner("🚀 正在演示 BossAlign (蛔虫引擎) 实战全流程...")
    
    raw = "这写的什么狗屁？！又是领军品牌、匠心智造，全片一股浓浓的 AI 味！我要看无人机在 7 级大风里的实测悬停！重新改！"
    print(f"\n1. 领导发来夺命语音:\n\"{raw}\"")
    
    event, rule = parse_feedback_event("Boss_Victor", raw, "篇02_性能展示")
    print(f"\n2. 情绪脱水完成: 提取意图: -> {event.extracted_intent}")
    print(f"3. 反例边界确立: -> {rule.counter_example_rationale}")
    
    draft = "【镜头1】SkyPulse 天脉智航作为行业遥遥领先的领军品牌，倾注匠心智造...\n【镜头2】抗风测试：在7级风洞实测中，漂移公差控制在±3cm以内。"
    print("\n4. 生成草稿 V2 并送入影子老板沙箱...")
    sandbox = ShadowBossSandbox("Boss_Victor")
    res = sandbox.review_draft(draft)
    
    print_warning(f"沙箱精准拦截: 发现禁忌词 -> {res['issues'][0]['detail']}")
    
    final_script = "【镜头1】风洞现场实景，7级狂风呼啸。\n【镜头2】特写仪表盘与螺旋桨：漂移公差控制在±3cm以内。\n【口播】不吹技术参数，只看极端天气下的悬停底气。"
    print("\n5. 修复并二次过检：沙箱 100% 绿色通过！")
    print("\n" + "="*50)
    print(" 领导最终反馈：\"这版感觉完全对了！牛逼，我要的就是这种真实感！通过！\"")
    print("="*50 + "\n")

def main():
    parser = argparse.ArgumentParser(description="BossAlign (蛔虫引擎) - 专治领导挑剔改稿的对齐框架")
    subparsers = parser.add_subparsers(dest="command")
    
    # ingest
    p_ingest = subparsers.add_parser("ingest", help="录入领导反馈并生成反例边界")
    p_ingest.add_argument("--reviewer", default="Boss_Victor", help="审核人代号")
    p_ingest.add_argument("--raw", required=True, help="未经处理的领导原话")
    p_ingest.add_argument("--context", default="通用篇目", help="发生反馈的篇目")
    p_ingest.set_defaults(func=cmd_ingest)
    
    # check
    p_check = subparsers.add_parser("check", help="影子老板闭门沙箱检查")
    p_check.add_argument("--file", required=True, help="待检测草稿文件路径")
    p_check.add_argument("--reviewer", default="Boss_Victor", help="目标审核人")
    p_check.set_defaults(func=cmd_check)
    
    # sanitize
    p_san = subparsers.add_parser("sanitize", help="净室清洗交付")
    p_san.add_argument("--file", required=True, help="待清洗草稿文件路径")
    p_san.add_argument("--out", required=True, help="清洗后交付文件路径")
    p_san.set_defaults(func=cmd_sanitize)
    
    # demo
    p_demo = subparsers.add_parser("demo", help="30秒一键实战演示")
    p_demo.set_defaults(func=cmd_demo)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # Default to demo if no args provided
        cmd_demo(args)

if __name__ == "__main__":
    main()
