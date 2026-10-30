"""Minimal image overlay for the <=50-user deployment authorized by the owner.

Keep upstream copyright/license files. Fail if the pinned upstream layout changes.
"""
from pathlib import Path
import os

if os.environ.get('INTECHA_REBRANDING_CONFIRMED') != 'small-scale-50':
    raise SystemExit('Rebranding requires the recorded <=50-user license exception')
root=Path('/app')
env=root/'backend/open_webui/env.py'
source=env.read_text()
old="if WEBUI_NAME != 'Open WebUI':\n    WEBUI_NAME += ' (Open WebUI)'"
if source.count(old)!=1:
    raise SystemExit('Upstream branding block changed: review before updating image')
env.write_text(source.replace(old,"# Intecha: small-scale branding exception, see /app/INTECHA-NOTICE.md"))
modified=0
for path in (root/'build').rglob('*'):
    if path.is_file() and path.suffix in ('.js','.html','.json','.webmanifest'):
        text=path.read_text()
        if 'Open WebUI' in text:
            path.write_text(text.replace('Open WebUI','Intecha'))
            modified+=1
            # Rebuilds carry new source hashes upstream; remove precompressed originals.
            for suffix in ('.gz','.br'):
                path.with_name(path.name+suffix).unlink(missing_ok=True)
if modified==0:
    raise SystemExit('No frontend branding found: inspect pinned upstream image')

# Repo-native mark, drawn from the geometry of the existing Intecha SVG asset.
from PIL import Image, ImageDraw
static=root/'build/static'
static.mkdir(exist_ok=True)
def icon(size=128,dark=False,background=True):
    scale=4
    im=Image.new('RGBA',(size*scale,size*scale),(0,0,0,0))
    d=ImageDraw.Draw(im)
    if background:d.rounded_rectangle((0,0,size*scale-1,size*scale-1),radius=24*scale,fill='#171717')
    color='white' if dark or background else '#171717'
    points=[(82,23),(47,23),(27,58),(47,93),(82,93)]
    points=[(int((x+8)*size*scale/128),int((y+6)*size*scale/128)) for x,y in points]
    d.line(points,fill=color,width=max(1,int(9*size*scale/128)),joint='curve')
    cx,cy=64*size*scale/128,64*size*scale/128;r=8*size*scale/128
    d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=color)
    return im.resize((size,size),Image.Resampling.LANCZOS)
for name,size in [('favicon.png',128),('favicon-96x96.png',96),('apple-touch-icon.png',180),('web-app-manifest-192x192.png',192),('web-app-manifest-512x512.png',512)]:
    icon(size).save(static/name)
icon(128).save(static/'favicon.ico',format='ICO')
icon(256,background=False).save(static/'splash.png')
icon(256,dark=True,background=False).save(static/'splash-dark.png')
(static/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" rx="24" fill="#171717"/><path d="M90 29H55L35 64 55 99H90" fill="none" stroke="white" stroke-width="9" stroke-linejoin="round"/><circle cx="64" cy="64" r="8" fill="white"/></svg>')
print(f'Intecha overlay applied to {modified} frontend assets; upstream notices preserved')
