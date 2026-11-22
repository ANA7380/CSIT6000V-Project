"""Rebuild the report's standalone vector diagrams with Python's standard library."""
from html import escape
from pathlib import Path
ROOT=Path(__file__).resolve().parent

class Diagram:
    def __init__(self,w,h,title):
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}"><defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" fill="#486477"/></marker></defs><rect width="100%" height="100%" fill="#fff"/><g font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" fill="#203643">']
        self.text(w/2,35,[title],22,'middle')
    def text(self,x,y,lines,size=15,anchor='middle',color='#203643'):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{color}">')
        for i,line in enumerate(lines):self.parts.append(f'<tspan x="{x}" dy="{0 if i==0 else size*1.45}">{escape(line)}</tspan>')
        self.parts.append('</text>')
    def area(self,x,y,w,h,title):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="#f4f7fa" stroke="#c9d7df"/>')
        self.text(x+18,y+28,[title],17,'start')
    def box(self,x,y,w,h,lines,kind='normal'):
        colors={'normal':('#fff','#8ca7b7'),'model':('#e8f2ff','#4b7ca9'),'tool':('#e9f5ee','#50856a'),'error':('#fff4e4','#ae8651')}
        fill,stroke=colors[kind];self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        self.text(x+w/2,y+h/2-(len(lines)-1)*11+5,lines)
    def arrow(self,points,label=None,lx=None,ly=None,dashed=False):
        pts=' '.join(f'{x},{y}' for x,y in points)
        self.parts.append(f'<polyline points="{pts}" fill="none" stroke="#486477" stroke-width="1.8" marker-end="url(#arrow)"'+(' stroke-dasharray="6 4"' if dashed else '')+'/>')
        if label:self.text(lx,ly,[label],13)
    def save(self,name):
        (ROOT/name).write_text(''.join(self.parts)+ '</g></svg>')

d=Diagram(1040,850,'前后端与 TACC 同作业部署')
d.area(25,65,380,650,'用户电脑')
d.area(460,65,555,650,'TACC 一个 GPU 作业')
d.box(60,125,310,80,['浏览器  chat.html','界面 会话 图表与证据'])
d.box(60,260,310,90,['web_bridge.py','本机 HTTP 127.0.0.1:8765','POST /ask  GET /reply/ID'])
d.box(60,420,310,70,['tcloud SDK','已有账户认证 上传与下载'])
d.box(500,125,470,70,['supervisor.py','模型就绪检查 进程监控与清理'])
d.box(500,260,470,80,['web_worker.py','扫描请求 恢复会话 生成回复'])
d.box(500,420,210,90,['ChatAgent','动态选工具与循环'],'model')
d.box(760,420,210,90,['Qwen / vLLM','127.0.0.1:42865/v1'],'model')
d.box(500,565,210,95,['确定性六个工具','TickerAgent','AnalysisTools'],'tool')
d.box(760,565,210,95,['三份冻结 CSV','财务快照与观察','复权日价格'],'tool')
d.arrow([(215,205),(215,260)],'本机 HTTP',270,237)
d.arrow([(215,350),(215,420)])
d.arrow([(370,455),(430,455),(430,740),(735,740),(735,785)],'认证文件传输',570,727)
d.arrow([(735,195),(735,260)],'监督',790,232,dashed=True)
d.arrow([(605,340),(605,420)])
d.arrow([(711,453),(760,453)],'请求',736,443)
d.arrow([(760,480),(711,480)],'结果',736,499)
d.arrow([(605,510),(605,565)])
d.arrow([(760,610),(710,610)])
d.area(25,760,990,75,'持久 USERDIR')
d.text(525,814,['stock-chat/NAMESPACE  请求 回复 状态 会话    |    stock-research/JOB_ID  日志 配置 验收'],14)
d.arrow([(980,785),(1000,785),(1000,305),(970,305)],'读写',973,745,dashed=True)
d.text(215,600,['电脑不直接访问计算节点模型端口','8765 与 42865 属于两台机器的回环地址'],14)
d.save('deployment.svg')

d=Diagram(1080,1130,'单 Agent 的有界工具反馈循环')
d.box(360,65,360,65,['A 接收问题 备份状态 turn ID'])
d.box(360,170,360,80,['B 构建上下文','唯一 system + 状态 + 历史'])
d.box(360,295,360,80,['C Qwen 决策','输出 tool 或 answer JSON'],'model')
d.box(360,420,360,65,['D 解析协议与白名单校验'])
d.box(40,550,390,75,['E 工具执行','校验参数 合并排名偏好'],'tool')
d.box(40,680,390,105,['F 保存证据与观察','E 编号 状态更新','追加 TOOL_RESULT'],'tool')
d.box(650,550,390,75,['G 最终解释校验','引用 ID 数字字符 URL'])
d.box(650,785,390,85,['H 合格回答 + 确定性证据','生成页面响应 保存快照'])
d.box(650,970,390,85,['有界降级或报错','保留已验证工具结果'],'error')
d.box(45,930,385,110,['循环上限 12 次模型调用','解释校验累计两次失败即降级','外围异常回滚本轮内存状态'],'error')
d.arrow([(540,130),(540,170)])
d.arrow([(540,250),(540,295)])
d.arrow([(540,375),(540,420)])
d.arrow([(420,485),(420,520),(235,520),(235,550)],'tool',300,511)
d.arrow([(660,485),(660,520),(845,520),(845,550)],'answer',791,511)
d.arrow([(235,625),(235,680)])
d.arrow([(40,730),(18,730),(18,210),(360,210)],'观察后再决策',170,281)
d.arrow([(360,450),(310,450),(310,265),(540,265),(540,295)],'MODEL_FORMAT_ERROR',170,408,dashed=True)
d.arrow([(845,625),(845,785)],'校验通过',895,710)
d.arrow([(1040,590),(1060,590),(1060,210),(720,210)],'首次失败后修正',883,248,dashed=True)
d.arrow([(650,600),(590,600),(590,1012),(650,1012)],'达到修正上限',536,905,dashed=True)
d.arrow([(430,985),(650,985)],'总预算耗尽',536,974,dashed=True)
d.text(540,1101,['蓝色节点才调用 LLM；绿色节点执行确定性算法；虚线表示错误反馈或上限分支'],14)
d.save('agent-loop.svg')

d=Diagram(1120,1010,'单次问题的异步传输时序')
xs=[100,325,560,795,1020]
names=[['浏览器','chat.html'],['本机网页桥','web_bridge'],['SDK 共享目录','USERDIR'],['服务器 worker','ChatAgent'],['Qwen','vLLM']]
for x,name in zip(xs,names):
 d.box(x-92,65,184,65,name)
 d.parts.append(f'<line x1="{x}" x2="{x}" y1="130" y2="955" stroke="#bacbd4" stroke-dasharray="5 5"/>')
def seq(a,b,y,label):d.arrow([(xs[a],y),(xs[b],y)],label,(xs[a]+xs[b])/2,y-10)
seq(0,1,180,'POST /ask')
seq(1,2,240,'1 上传 ID.request')
seq(1,2,300,'2 上传 ID.ask 标记')
seq(1,0,355,'202 + request ID')
seq(2,3,410,'扫描标记 读取问题')
seq(3,4,470,'messages 决策请求')
seq(4,3,530,'tool 或 answer JSON')
d.box(680,560,225,100,['校验并执行工具','保存证据与状态','TOOL_RESULT 回到模型'],'tool')
seq(0,1,600,'轮询 GET /reply/ID')
seq(2,1,650,'下载 status 返回 202')
seq(3,4,705,'必要时继续决策')
seq(4,3,765,'最终解释')
seq(3,2,825,'保存 state 与 ID.reply')
seq(0,1,885,'GET /reply/ID')
seq(2,1,935,'SDK 下载 reply')
seq(1,0,985,'200 + 解释 证据 图表')
d.save('request-sequence.svg')
