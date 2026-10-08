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
    draw.text((60,35),'飞鹰 / 天空箭头 + 精简地面引导',font=TITLE,fill='#ecffff')
    draw.text((62,92),'1.9.7 源码几何示意 · 密排填充 · 非实机截图',font=BODY,fill='#80b8c8')
    panels=[(150,440,'天空 · 竖直 → 箭头 / 带箭杆 / 沿来袭方向移动'),
            (480,770,'地面 · 小型流动箭头 / 细边界 / 紧凑金色落点'),
            (810,1100,'飞机 · 保留现有机头指引')]
    for top,bottom,label in panels:
        draw.rectangle((40,top,1460,bottom),fill='#0b1d28',outline='#224352')
        draw.text((65,top+20),label,font=BODY,fill='#b4f0ff')
    segments=design_geometry(phase)
    palette={'air':(255,255,255,220),'ground':(255,255,255,235),
             'flow':(230,255,255,235),'holo':(80,220,255,100),
             'trail':(150,220,255,55),'marker':(255,210,90,255),
             'sky_edge':(80,220,255,65)}
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
    draw.text((65,730),'显示宽 12 m；箭头填实，落点为约 2.8 m 的金色菱形。',font=SMALL,fill='#80b8c8')
    draw.text((65,1060),'后伸 220 m、前伸 120 m；确认离场后，天空和地面指引同步消失。',font=SMALL,fill='#80b8c8')
    draw.text((60,1140),'MODS → 飞鹰方向指引：透视默认关闭 · 天空箭头 / 地面走廊可分别切换',font=BODY,fill='#b4cbd2')
    return image


def main():
    target=ROOT/'docs/holographic-geometry.png'
    target.parent.mkdir(parents=True,exist_ok=True)
    frames=[render(i*(28/6)/24) for i in range(24)]
    frames[0].save(target)
    animation=ROOT/'docs/holographic-motion.gif'
    frames[0].save(animation,save_all=True,append_images=frames[1:],duration=194,loop=0,optimize=True)
    print(target)
    print(animation)


if __name__=='__main__':
    main()
