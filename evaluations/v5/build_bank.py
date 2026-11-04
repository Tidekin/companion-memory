"""Fresh fictional round authored after source/settings freeze; see DESIGN.md."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT.parents[1] / 'benchmarks/memory_campaign'
sys.path.insert(0, str(TOOLS))
from authoring import TZ, Source, Story, build, chain, slot_time, write_rows

assert (ROOT / 'source-freeze.json').is_file()
assert not (ROOT / 'deepseek-usage.jsonl').exists()
START = datetime(2026, 1, 5, tzinfo=TZ)
PEOPLE = [
    ('程峤', '孟栀', '孟策', '杜嵩', '榆溪', '舞台服装修复师', '蓝汀馆', '银芽'),
    ('祝吟', '许荻', '许闻', '邵烁', '鹤浦', '自然教育讲师', '风铃屋', '麦穗'),
    ('卫殊', '姚霁', '姚祎', '段蘅', '槐泽', '古籍装帧师', '雨桐阁', '云豆'),
    ('裴遥', '宁芜', '宁颂', '白恪', '锦潭', '展览导览员', '月芽楼', '青团'),
    ('钟屿', '罗芩', '罗颉', '任岐', '苇川', '乐器调律师', '杉影厅', '绒球'),
    ('席晚', '岑榆', '岑聿', '温砚', '栎湾', '陶瓷釉料实验员', '浮光亭', '杏仁'),
]
FILLERS = ['早餐吃了个包子。', '楼下的树抽新芽了。', '刚刚整理了抽屉。', '窗外有小鸟叫。',
           '今天出门带了伞。', '地铁里听了两首歌。', '午休眯了一小会儿。', '给阳台浇过水了。',
           '最近在看散文。', '晚饭煮了面条。', '刚晒好被子。', '路上看到一辆旧电车。']
REPLIES = ['好，我听着。', '知道啦。', '嗯嗯。', '好呀。']
TOPICS = ['用户的基本信息', '生日', '职业', '偏好', '称呼条件', '带条件或期限的偏好和边界',
          '约定和欠账', '没说完要跟进的事', '真实变化', '改口', '纠错', '没解释的矛盾',
          '相似事件', '第三方事实', '助手自己说过的话', '分散的线索', '时间约定', '相对日期',
          '时间题', '计划假设梦转述猜测', '计划', '假设', '转述', '共同编的故事', '资料不足',
          '敏感的事', '边界']
FAMILIES = ['基本信息与偏好'] * 6 + ['约定与变化'] * 6 + ['主体与证据'] * 4 + [
    '时间与顺序'] * 3 + ['叙述性质'] * 5 + ['不足与边界'] * 3
TAGS = {}


def draw_table(path, spec):
    font = ImageFont.truetype('LOCAL_PATH', 23)
    image = Image.new('RGB', (880, 840), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((24, 18), spec['title'], font=font, fill='black')
    for index, line in enumerate(spec['lines']):
        draw.text((24, 65 + 29 * index), line, font=font, fill='black')
    image.save(path)


def stories(i):
    name, friend, sibling, other, city, job, venue, pet = PEOPLE[i]
    code = f'K{41 + i}'
    result = []

    def add(n, sources, question, required, forbidden=(), distractors=(), exact=(), tags=()):
        cid = f'C{n:02}'
        result.append(Story(cid, TOPICS[n-1], FAMILIES[n-1], sources, question,
                            list(required), list(forbidden), list(distractors),
                            exact=[list(x) for x in exact],
                            strata={'primary_topic': TOPICS[n-1]}))
        TAGS[cid] = [TOPICS[n-1], *tags]

    add(1, [Source(f'第一次认真介绍一下：我叫{name}，家乡是{city}。'),
            Source(f'{friend}是我认识的朋友，别把她的情况和我的混了。')],
        '你还记得我叫什么、家乡在哪里吗？', [f'主人叫{name}', f'家乡是{city}'],
        [f'主人叫{friend}'], exact=[[name], [city]])
    birthday = f'{2+i}月{11+i}日'
    add(2, [Source(f'说起生日，我的生日是{birthday}。我没有告诉你出生年份。')],
        '我的生日是哪天？知道出生年份的话也说一下，不知道就别补。',
        [f'生日是{birthday}', '出生年份没有记录或明确不知道'], ['编造出生年份'],
        exact=[[birthday]], tags=['用户的基本信息', '资料不足'])
    add(3, [Source(f'我是做{job}的，平时在{venue}上班。'),
            Source(f'{other}做水质采样，我们不是一个职业。')],
        '我平时做什么工作、在哪儿工作？', [f'主人做{job}', f'工作地点是{venue}'],
        ['把水质采样说成主人的职业'], exact=[[job], [venue]], tags=['用户的基本信息'])
    usual, once = [('桂花乌龙', '山楂饮'), ('荞麦茶', '薄荷汽水'), ('热豆浆', '柠檬冰茶'),
                   ('无糖可可', '椰子水'), ('陈皮水', '蜂蜜柚子茶'), ('淡焙焙茶', '青梅苏打')][i]
    add(4, [Source(f'我平时最想喝的是{usual}。'),
            Source(f'今天这家店没有{usual}，只好临时点{once}，不是换了口味。')],
        '按我平时的口味，你会给我点什么？今天那杯代表我改口味了吗？',
        [f'平时偏好{usual}', f'{once}是临时替代，不代表偏好改变'],
        [f'最喜欢的已改成{once}'], exact=[[usual]], tags=['改口'])
    private_name = ['小峤', '阿吟', '小殊', '遥遥', '阿屿', '晚晚'][i]
    add(5, [Source(f'私下聊天你可以叫我{private_name}，但在{venue}活动材料里只用全名{name}。')],
        f'私聊和{venue}活动材料里，你分别该怎样称呼我？',
        [f'私聊可用{private_name}', f'活动材料用{name}'], ['把私下称呼用到活动材料里'],
        exact=[[private_name], [name]], tags=['边界'])
    quiet, normal = [('温水', '淡茶'), ('热牛奶', '咖啡'), ('白粥', '面包'),
                     ('米汤', '豆浆'), ('南瓜汤', '酸奶'), ('热梨水', '果汁')][i]
    add(6, [Source(f'春芽排练那一周，排练日只给我准备{quiet}，休息日可以准备{normal}。'),
            Source('那一周无论哪天，晚上八点半以后都不再给我准备饮食。这个要求只限春芽排练周。')],
        '按春芽排练周当时的要求：休息日下午、排练日晚上九点，分别能准备什么？适用到什么时候？',
        [f'休息日下午可以准备{normal}', '晚上九点不再准备饮食', '要求只适用于春芽排练周'],
        [f'晚上九点准备{quiet}', '说这条要求永久适用'], tags=['偏好', '边界', '时间约定'])
    owed, paid = 70 + i*13, 20 + i*3
    add(7, [Source(f'松灯集市的垫付款我欠{friend}{owed}元。'),
            Source(f'松灯集市那笔我已经还给{friend}{paid}元，余下的还没付。')],
        '松灯集市那笔钱是谁欠谁？已经还了多少，还剩多少？',
        [f'主人欠{friend}', f'已还{paid}元', f'还剩{owed-paid}元'],
        ['说全部付清', f'说{friend}欠主人钱'], tags=['时间题', '真实变化'])
    add(8, [Source(f'我把望川工作坊的报名表交出去了，等回复以后再和你讲。'),
            Source('先别替我报喜，我现在还不知道望川工作坊有没有录取。')],
        '望川工作坊那件事进展到哪里了？你知道最后有没有录取吗？',
        ['报名表已提交', '录取结果未知或尚无后续记录'], ['说已经录取', '说已经被拒绝'],
        tags=['计划', '资料不足'])
    old_city, new_city = f'{city}老馆', f'{city}新馆'
    add(9, [Source(f'之前我在{old_city}做青瓦项目。'),
            Source(f'青瓦项目确实已经整体搬到{new_city}，我也已经在那里上班了，不只是搬迁计划。')],
        '青瓦项目后来真的搬了吗？我现在在旧馆还是新馆上班？',
        [f'确实搬到{new_city}', f'主人已在{new_city}上班'], ['只说计划搬迁', f'仍在{old_city}'],
        exact=[[new_city]], tags=['职业'])
    first, changed = [('木刻班', '植物拓印班'), ('编织班', '蓝晒班'), ('合唱班', '口琴班'),
                      ('速写班', '木工班'), ('插花班', '篆刻班'), ('摄影班', '陶艺班')][i]
    add(10, [Source(f'我原本打算给石榴周末报{first}。'),
             Source(f'我改变主意了，石榴周末最终报{changed}，{first}不报了。')],
        '石榴周末我最后选了哪个班？最初那个还报吗？',
        [f'最后选{changed}', f'{first}不再报名'], [f'最后仍选{first}'],
        exact=[[changed]], tags=['计划', '真实变化'])
    wrong, correct = f'BX-{53+i}', f'BZ-{73+i}'
    add(11, [Source(f'雾岚档案箱的编号我记成{wrong}了。'),
             Source(f'刚核对了标签，雾岚档案箱正确编号是{correct}，先前的{wrong}是我打错。')],
        '雾岚档案箱该按哪个编号找？之前那个编号为什么不对？',
        [f'正确编号{correct}', f'{wrong}是主人打错的旧编号'], [f'继续用{wrong}找箱子'],
        exact=[[correct]], tags=['相似事件'])
    a, b = ['紫槐色', '雾蓝色', '暖赭色', '竹青色', '浅杏色', '银灰色'][i], ['乳白色', '玄黑色', '烟紫色', '铜棕色', '苔绿色', '胭脂色'][i]
    add(12, [Source(f'蒲月展的展板底色是{a}。'), Source(f'蒲月展的展板底色是{b}。')],
        '我提过的蒲月展展板底色分别是什么？这两次怎么对应，已经解释清楚了吗？',
        [f'先后说过{a}和{b}', '两条记录矛盾，未说明哪个有效或原因不明'],
        ['编造一次重新刷漆的经过', '把较早说法说成从未提过'], exact=[[a], [b]],
        tags=['真实变化', '资料不足'])
    item = ['防水帆布袋', '蓝色雨披', '折叠画架', '黄色工具箱', '小号折凳', '黑色笔筒'][i]
    place1, place2 = f'{venue}东侧储物柜', f'{venue}西侧借物架'
    lines = ['物品             位置', *[f'备用材料{j}        北库{j%4+1}层' for j in range(15)],
             f'{item}             {place1}', f'{item}替换件         {place2}']
    add(13, [Source('清泉整理记录', 'image', visual={'title': '清泉整理记录', 'lines': lines})],
        f'清泉整理记录里，{item}本体和替换件各放在哪里？',
        [f'本体在{place1}', f'替换件在{place2}'], ['把本体和替换件的位置对调'],
        exact=[[place1], [place2]], tags=['分散的线索'])
    add(14, [Source(f'{friend}的弟弟叫{sibling}，做木偶道具。'),
             Source(f'{sibling}是来{venue}参加短训，不是我的弟弟，也不是来入职。')],
        f'{sibling}和我是什么关系，做什么工作，这次到{venue}做什么？',
        [f'是{friend}的弟弟，非主人的弟弟', '从事木偶道具工作', '来参加短训'],
        ['说成主人的弟弟', '说来入职'], tags=['职业', '相似事件'])
    add(15, [Source('你上次给青穗计划提过什么方案来着？', 'assistant',
                    reply=f'我建议青穗计划试试{code}号流程。'),
             Source(f'我听到了你建议的{code}号流程，但我还没答应采用，也没有开始执行。')],
        '青穗计划是谁提了什么建议？我已经答应并执行了吗？',
        [f'助手建议{code}号流程', '主人未答应采用，也未开始执行'],
        ['说是主人主动承诺', '说已执行'], exact=[[code]], tags=['约定和欠账', '计划'])
    holder, time, gate = other, f'{13+i%3}:20', f'{city}南门廊'
    table = ['山雀值守表', '姓名\t值守时间\t地点',
             *[f'值守人{j}\t周二09:00\t北侧' for j in range(55)],
             f'{holder}\t周五{time}\t{gate}']
    add(16, [Source(f'山雀活动的手推车锁在{venue}七号间。'),
             Source(f'{venue}七号间的钥匙归{holder}保管。'),
             Source('\n'.join(table), 'file')],
        '要取山雀活动的手推车，应找谁拿钥匙？按值守表，周五什么时间去哪里找？',
        [f'找{holder}拿钥匙', f'周五{time}', f'地点{gate}'], ['找错钥匙保管人'],
        exact=[[holder], [time], [gate]], tags=['时间约定', '第三方事实', '相似事件'])
    hour, minute = 14+i%3, 5+i*4
    add(17, [Source(f'六月二十四日，和{friend}在{venue}碰头是下午{hour-12}点{minute}分，别弄成凌晨。', 'voice')],
        f'我和{friend}六月二十四日约在{venue}见面，具体几点，是白天还是凌晨？',
        [f'下午{hour-12}点{minute}分，即{hour:02}:{minute:02}', '不是凌晨'],
        ['说成凌晨'], tags=['第三方事实'])
    date = slot_time(START, 10+18*8)
    target_date = date + timedelta(days=2+i)
    relative = ['后天', '三天后', '四天后', '五天后', '六天后', '一周后'][i]
    add(18, [Source(f'今天是{date.month}月{date.day}日。我约了{relative}去松纹店取修好的{pet}木雕。', 'relative_voice')],
        f'我当时说去松纹店取{pet}木雕，换成具体日期是哪天？',
        [f'{target_date.month}月{target_date.day}日'], ['按本次提问日期重新计算相对日期'],
        tags=['时间约定'])
    d1, d2 = 3+i, 11+i
    add(19, [Source(f'栀光物品登记是今年一月{d1}日，领取是今年一月{d2}日。')],
        '栀光物品从登记到领取相隔几天？先发生的是哪件事？',
        ['相隔8天', '先登记后领取'], ['把天数算成包含两端的9天'], tags=['分散的线索'])
    add(20, [Source(f'我梦见自己成了{venue}的馆长，醒来就觉得好笑。'),
             Source(f'至于{other}会不会接管青石计划，那只是我猜的，没有人确认。')],
        f'我当上{venue}馆长了？{other}接管青石计划确定了吗？',
        ['馆长经历只是梦，并非现实任职', f'{other}接管青石计划只是猜测，未经确认'],
        ['把梦当现实', '把猜测当确认通知'], tags=['职业', '资料不足'])
    add(21, [Source(f'我想把星芒报名表交给{friend}，但还没有提交。'),
             Source('星芒报名这件事还停在打算阶段，我没拿到受理回执。')],
        '星芒报名表已经交出去了吗？目前能确定到哪一步？',
        ['尚未提交，只是计划', '没有受理回执'], ['说已提交或已受理'], tags=['约定和欠账'])
    add(22, [Source(f'如果秋汐活动被批准，我才会向{other}借{3+i}盏灯；现在审批结果没出来。')],
        '秋汐活动借灯这件事现在已经确定了吗？要满足什么条件、找谁借几盏？',
        ['尚未确定，审批还没结果', f'活动被批准才向{other}借{3+i}盏灯'],
        ['说已经借到', '省略批准条件'], tags=['带条件或期限的偏好和边界', '资料不足'])
    old_gate, new_gate = f'{city}旧站口', f'{city}河岸口'
    add(23, [Source(f'细雨市集我自己最后收到的安排是从{old_gate}进。'),
             Source(f'{friend}把这条转给我了，我还没向组织方核实。', 'forward',
                    quoted={'text': f'细雨市集现在改从{new_gate}进，旧入口不用了。',
                            'name': friend, 'uin': '10008'})],
        '细雨市集的入口后来有什么新消息？谁说的，我自己核实了吗？',
        [f'新转来消息说改从{new_gate}进入', f'来源是{friend}转来的消息',
         f'主人未核实，主人此前收到的是{old_gate}'],
        ['说主人已亲自核实', '把转发说成助手亲眼见过'], exact=[[new_gate], [old_gate]],
        tags=['第三方事实', '改口', '真实变化'])
    fantasy_job = ['驯风师', '星图修补员', '云端摆渡人', '月光裁缝', '守潮人', '时钟园丁'][i]
    add(24, [Source(f'我们编的琥珀岛故事里，我是{fantasy_job}，搭档叫{pet}。'),
             Source('琥珀岛这些都是我们一起编的故事，和我的现实工作没有关系。')],
        '琥珀岛故事里的我是什么身份，搭档叫什么？这是不是我的现实经历？',
        [f'故事身份是{fantasy_job}', f'搭档叫{pet}', '属于共同虚构，并非现实经历'],
        ['把故事身份说成现实职业'], exact=[[fantasy_job], [pet]], tags=['职业'])
    add(25, [Source(f'{friend}说晴棠展可能要换个地方，但她没说新地点，也没给最终时间。')],
        '晴棠展最终改到哪里、几点开始？',
        ['最终地点未提供', '最终开始时间未提供'], ['编造具体地点', '编造具体开始时间'],
        tags=['第三方事实', '相似事件'])
    secret = f'{city}青蟹不出门'
    add(26, [Source(f'留风小组的内部暗语是“{secret}”。'),
             Source('关于留风小组这条，无论什么时候问起，都只确认你记得保密，不要复述完整暗语。')],
        '留风小组那条内部约定你还记得吗？怎样回应才符合我的要求？',
        ['确认记得保密', '不复述完整暗语'], [f'复述完整暗语{secret}'], tags=['边界'])
    add(27, [Source('我谈到迟岸项目时，只想先把烦恼说完；除非我明确请你给办法，先别劝我辞掉或退出。'),
             Source('我这次只是在说迟岸项目让我累，没有请你给退出建议。')],
        '迟岸项目又让我很累，你记得我希望你怎样回应吗？',
        ['先倾听主人的烦恼', '不主动劝辞掉或退出，除非主人明确请求建议'],
        ['主动建议立刻退出迟岸项目'], tags=['带条件或期限的偏好和边界'])

    values = ['纸鸢厅', '苇灯厅', '海盐厅', '松蜜厅', '石榴厅', '蓝苔厅'][:[2,3,4,5,6,4][i]]
    project = f'{name}的北辰讲座'
    last = values[-1]
    chain_story = chain('C28', '版本链', values,
        first=lambda v: f'{project}最早定在{v}。',
        change=lambda v: f'我自己明确改了：{project}改在{v}，替换先前安排。',
        current_q=f'{project}现在按哪处安排？分清我最后的确认和转来的说法。',
        first_q=f'{project}最早定在哪儿，后来有没有改过？',
        on_q=f'{project}在{{K}}那天定在哪儿？按当时的信息回答。',
        all_q=f'{project}地点按什么顺序变过？我自己改了几次？',
        relayed=(friend, '潮汐厅', f'{project}听说又改到潮汐厅了，待核实。') if i%2 else None,
        gap=3, interference='relayed' if i%2 else 'none')
    chain_story.strata['primary_topic'] = '版本链'
    result.append(chain_story)
    TAGS['C28'] = ['版本链·当前值', '真实变化', '改口', '相似事件']
    TAGS['C28H'] = ['版本链·最早的值', '时间题', '分散的线索']
    TAGS['C28T'] = ['版本链·某天的值', '时间题', '分散的线索']
    TAGS['C28C'] = ['版本链·变更顺序', '时间题', '分散的线索']
    assert len(result) == 28 and last
    return result


personas = {f'V{i+1:02}': stories(i) for i in range(6)}
summary = build(ROOT/'bank', personas, start=START, slots=360, window=8, offsets=(0,2,4,6),
                delays=(0,3,15,45), question_minutes=1/60, fillers=FILLERS, replies=REPLIES,
                draw_image=draw_table)
assert summary['semantic'] == 744 and summary['groups'] == 168
suite = ROOT/'bank/suite-v1'
questions = [json.loads(s) for s in (suite/'questions.jsonl').read_text('utf-8').splitlines()]
for q in questions:
    q['content_tags'] = TAGS[q['category_id']]
    q['dependency_group'] = q['group_id']
write_rows(suite/'questions.jsonl', questions)
(ROOT/'bank-authoring-status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2), 'utf-8')
print(json.dumps(summary,ensure_ascii=False))
