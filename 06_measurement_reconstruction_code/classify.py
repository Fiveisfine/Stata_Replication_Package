"""Versioned, outcome-blind category rules; labels take precedence over names.

Type codes are retained, normalized and profiled, but are not assumed to have a
universal cross-provider meaning. A name fallback is separate from strict labels.
"""
import re
import numpy as np
import pandas as pd

RULE_VERSION = '20261114.1'
PATTERNS = {
    'retail': r'烟酒|烟草专卖|烟草零售|酒类专卖|酒类零售|酒类销售|酒类商店|酒水专卖',
    'bar': r'酒吧|酒馆|清吧|餐吧|音乐酒吧',
    'nightclub': r'夜总会|夜店',
    'ktv': r'KTV|卡拉\s*OK|卡拉喔凯|歌厅|练歌房',
    'disco': r'迪厅|迪斯科|歌舞厅|舞厅|蹦迪',
}
NAME_PATTERNS = {
    'retail': r'烟酒|酒类专卖|酒水专卖|酒类商行|酒水商行|名酒专卖',
    'bar': r'酒吧|酒馆|清吧',
    'nightclub': r'夜总会|夜店',
    'ktv': r'KTV|卡拉\s*OK|歌厅|练歌房',
    'disco': r'迪厅|迪斯科|歌舞厅|舞厅',
}
EXCLUDE_NAME = r'酒厂|酿酒厂|酒业公司|酒业有限公司|酒业集团|舞蹈培训|舞蹈学校|舞蹈工作室|培训学校'
OLD_PATTERN = r'酒吧|酒馆|酒楼|啤酒|白酒|红酒|葡萄酒|烟酒|酒水|酒业|酒行|酒庄|酒厂|酒类|名酒|酒窖|洋酒|黄酒'


def classify(frame):
    name = frame['name'].fillna('').astype(str)
    cat = frame['category'].fillna('').astype(str)
    flags = np.zeros(len(frame),dtype=np.uint16)
    assisted = np.zeros(len(frame),dtype=np.uint16)
    for k,(key,pattern) in enumerate(PATTERNS.items()):
        strict = cat.str.contains(pattern,case=False,regex=True,na=False).to_numpy()
        fallback = name.str.contains(NAME_PATTERNS[key],case=False,regex=True,na=False).to_numpy()
        fallback &= ~name.str.contains(EXCLUDE_NAME,case=False,regex=True,na=False).to_numpy()
        if key == 'disco':
            strict &= ~cat.str.contains('培训|学校|舞蹈教室',regex=True,na=False).to_numpy()
        flags |= strict.astype(np.uint16) << k
        assisted |= (strict|fallback).astype(np.uint16) << k
    text = name+';'+cat
    # Bits 5/6/7 are general controls; bit 8 reproduces the old keyword definition.
    for bit,pat in [(5,r'餐饮|美食|饭店|餐厅|火锅|小吃|咖啡|茶馆|饮品|甜品'),(6,r'体育休闲|休闲娱乐|影剧院|电影院|KTV|歌厅|网吧|棋牌|游乐|洗浴|足浴|旅游景点|风景名胜'),(7,r'购物|商场|超市|便利店|专卖店|商城|市场'),(8,OLD_PATTERN)]:
        flags |= text.str.contains(pat,case=False,regex=True,na=False).to_numpy().astype(np.uint16) << bit
    return flags, assisted


def fixture_check():
    f=pd.DataFrame([
        {'name':'某酒厂','category':'公司企业;工厂'},
        {'name':'某烟酒专卖店','category':'购物服务;专卖店;烟酒专卖店'},
        {'name':'某KTV','category':'体育休闲服务;娱乐场所;KTV'},
        {'name':'某普通酒楼','category':'餐饮服务;中餐厅'},
        {'name':'某舞蹈学校','category':'教育培训;舞蹈培训'},
        {'name':'某夜总会','category':'休闲娱乐;夜总会'},
        {'name':'某迪厅','category':'体育休闲服务;迪厅'},
        {'name':'某酒吧','category':'体育休闲服务;酒吧'},
    ])
    s,a=classify(f)
    assert list(s&31)==[0,1,8,0,0,4,16,2]
    assert list(a&31)==[0,1,8,0,0,4,16,2]
    return f.assign(strict_mask=s,assisted_mask=a)
