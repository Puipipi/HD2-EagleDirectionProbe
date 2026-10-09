"""Preview shipped line geometry, including the cached moving-arrow path."""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_visual_geometry import design_geometry

ROOT=Path(__file__).resolve().parents[2]
FONT='C:/Windows/Fonts/msyh.ttc'
TITLE=ImageFont.truetype(FONT,36)
BODY=ImageFont.truetype(FONT,23)
SMALL=ImageFont.truetype(FONT,19)


def render(phase):
    image=Image.new('RGBA',(1500,1200),'#07141c')
    draw=ImageDraw.Draw(image)
    draw.text((60,35),'飞鹰 / 红色全息警戒带 + 方向指引',font=TITLE,fill='#ecffff')
    draw.text((62,92),'1.9.9 源码几何示意 · 密排填充 · 非实机截图',font=BODY,fill='#80b8c8')
    panels=[(150,440,'天空 · 竖直 → 箭头 / 带箭杆 / 沿来袭方向移动'),
            (480,770,'地面 · 加粗实线 / 断续红色光片 / 放大三角'),
            (810,1100,'飞机 · 保留现有机头指引')]
    for top,bottom,label in panels:
        draw.rectangle((40,top,1460,bottom),fill='#0b1d28',outline='#224352')
        draw.text((65,top+20),label,font=BODY,fill='#b4f0ff')
    segments=design_geometry(phase)
    palette={'air':(255,255,255,220),'ground':(255,255,255,235),
             'flow':(230,255,255,235),'holo':(80,220,255,100),
             'trail':(150,220,255,55),'marker':(255,210,90,255),
             'sky_edge':(80,220,255,65),'cordon':(255,40,60,205),
             'cordon_dim':(255,30,50,65),'cordon_text':(255,160,150,245)}
    overlay=Image.new('RGBA',image.size)
    ink=ImageDraw.Draw(overlay)
    for kind,a,b in segments:
        if kind.startswith('sky'):
            scale,cx,cy,zbase=6,750,307,12
            if kind[-1].isdigit():
                alpha=int(160+70*(0.5+0.5*math.sin(phase*2-int(kind[-1])*0.9)))
                color=(235,255,255,alpha)
            else:
                color=palette[kind]
        elif max(a[2],b[2])<12:
            scale,cx,cy,zbase=3.8,750,635,0.8
            color=palette[kind]
        else:
            scale,cx,cy,zbase=2.5,820,965,80
            color=palette[kind]
        pa=(cx+a[0]*scale,cy-a[1]*scale-(a[2]-zbase)*scale)
        pb=(cx+b[0]*scale,cy-b[1]*scale-(b[2]-zbase)*scale)
        ink.line((pa,pb),fill=color,width=2)
    image=Image.alpha_composite(image,overlay).convert('RGB')
    draw=ImageDraw.Draw(image)
    draw.text((65,400),'侧面看是 →；单层竖直平面，中心离地约 12 m，复用地形缓存。',font=SMALL,fill='#80b8c8')
    # Enlarged side view of actual cached tape/text segments near the beacon.
    draw.rectangle((1050,590,1425,710),fill='#07141c',outline='#713d4a')
    for kind,a,b in segments:
        if kind.startswith('cordon') and a[1]<0:
            # The negative side reads left to right when seen from outside.
            if a[0]>b[0]:
                a,b=b,a
            if b[0]<-2.7 or a[0]>2.7:
                continue
            x0,x1=max(-2.7,a[0]),min(2.7,b[0])
            dx=b[0]-a[0]
            z0=a[2]+(b[2]-a[2])*(x0-a[0])/dx if dx else a[2]
            z1=a[2]+(b[2]-a[2])*(x1-a[0])/dx if dx else b[2]
            draw.line((1235+x0*65,700-(z0-0.8)*65,
                       1235+x1*65,700-(z1-0.8)*65),fill=palette[kind],width=2)
    draw.text((1065,565),'警戒带近景 · 类型尚未识别',font=SMALL,fill='#ffaaa9')
    draw.text((65,730),'三角 5.2 × 5.8 m；地面和天空箭头同步以 10 m/s 顺向移动。',font=SMALL,fill='#80b8c8')
    draw.text((65,1060),'后伸 220 m、前伸 120 m；确认离场后，天空和地面指引同步消失。',font=SMALL,fill='#80b8c8')
    draw.text((60,1140),'MODS → 飞鹰方向指引：透视默认关闭 · 天空箭头 / 地面走廊可分别切换',font=BODY,fill='#b4cbd2')
    return image


def main():
    target=ROOT/'docs/holographic-geometry.png'
    target.parent.mkdir(parents=True,exist_ok=True)
    frames=[render(i*(28/10)/24) for i in range(24)]
    frames[0].save(target)
    animation=ROOT/'docs/holographic-motion.gif'
    frames[0].save(animation,save_all=True,append_images=frames[1:],duration=117,loop=0,optimize=True)
    print(target)
    print(animation)
    detail=ROOT/'docs/cordon-panels-preview.png'
    render_cordon_detail().save(detail)
    print(detail)


def render_cordon_detail():
    canvas=Image.new('RGBA',(1500,820),'#07141c')
    draw=ImageDraw.Draw(canvas)
    draw.text((60,35),'断续红色光片 / 长边封锁指示',font=TITLE,fill='#ecffff')
    draw.text((60,95),'1.9.9 源码几何预览 · 非实机截图 · 当前仍使用线段渲染',font=BODY,fill='#80b8c8')
    segments=design_geometry(0)
    palette={'ground':(255,255,255,205),'flow':(230,255,255,235),
             'marker':(255,210,90,240),'cordon':(255,40,60,205),
             'cordon_dim':(255,30,50,65),'cordon_text':(255,160,150,245)}
    def project(p):
        return (750+p[0]*13+p[1]*7,360+p[1]*10-p[2]*45)
    for x in range(-40,41,10):
        draw.line((project((x,-10,0)),project((x,10,0))),fill='#16303b')
    for y in range(-10,11,5):
        draw.line((project((-45,y,0)),project((45,y,0))),fill='#16303b')
    for kind,a,b in sorted(segments,key=lambda s:(s[1][1]+s[2][1])/2):
        if kind not in palette or abs(a[0])>45 or abs(b[0])>45:
            continue
        layer=Image.new('RGBA',canvas.size)
        ImageDraw.Draw(layer).line((project(a),project(b)),fill=palette[kind],width=2)
        canvas=Image.alpha_composite(canvas,layer)
    draw=ImageDraw.Draw(canvas)
    draw.text((60,510),'每侧 7 块光片，间隔 30 m；落点附近为稍高的标签片。',font=BODY,fill='#b4f0ff')
    draw.text((60,552),'白色实线保留；移除交叉斜纹；光片间留出约 20 m 的视野空隙。',font=BODY,fill='#80b8c8')
    draw.text((60,620),'标签近景',font=BODY,fill='#ffaaa9')
    # Front elevation: actual central panel, enlarged without smoothing the lines.
    layer=Image.new('RGBA',canvas.size)
    ink=ImageDraw.Draw(layer)
    for kind,a,b in segments:
        if kind.startswith('cordon') and a[1]<0 and abs(a[0])<=3 and abs(b[0])<=3:
            ink.line((970+a[0]*55,770-(a[2]-0.8)*100,
                      970+b[0]*55,770-(b[2]-0.8)*100),fill=palette[kind],width=2)
    canvas=Image.alpha_composite(canvas,layer)
    draw=ImageDraw.Draw(canvas)
    draw.text((60,670),'具体类型暂未可靠识别，',font=BODY,fill='#80b8c8')
    draw.text((60,708),'目前显示 EAGLE ?。',font=BODY,fill='#80b8c8')
    return canvas.convert('RGB')


if __name__=='__main__':
    main()
