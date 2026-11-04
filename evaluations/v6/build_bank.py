"""Fresh stories authored after source/settings freeze; never used for tuning."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'benchmarks/memory_campaign'))
from authoring import TZ, Source, Story, build, chain, slot_time, write_rows

assert (ROOT / 'source-freeze.json').is_file()
assert not (ROOT / 'deepseek-usage.jsonl').exists()
START = datetime(2026, 1, 12, tzinfo=TZ)
PEOPLE = [('白栖', '鲁苒', '鲁拓', '郑骁', '云川', '纸伞修复师', '青榆伞坊', '豌豆'), ('辛棠', '金禾', '金骐', '陈朔', '澄汀', '石刻拓片员', '砚雨阁', '柿子'), ('伍漪', '施芙', '施越', '韩峪', '槲溪', '鸟类标本管理员', '羽影馆', '榛果'), ('翟宁', '范菁', '范原', '贝枢', '石浦', '舞台音响师', '雾桥剧院', '糯米'), ('许琛', '戴曦', '戴岚', '程遥', '枫津', '手工造纸师', '纸萤社', '杏脯'), ('桑澜', '韦葵', '韦岳', '吴峤', '鹭湾', '天文展教员', '星脊馆', '芒果')]
TOPICS = ['用户的基本信息', '生日', '职业', '偏好', '称呼条件', '带条件或期限的偏好和边界',
          '约定和欠账', '没说完要跟进的事', '真实变化', '改口', '纠错', '没解释的矛盾',
          '相似事件', '第三方事实', '助手自己说过的话', '分散的线索', '时间约定', '相对日期',
          '时间题', '计划假设梦转述猜测', '计划', '假设', '转述', '共同编的故事', '资料不足',
          '敏感的事', '边界', '版本链', '共同经历的续聊', '隐含偏好与未完成计划']
FAMILIES = ['基本信息与偏好'] * 6 + ['约定与变化'] * 6 + ['主体与证据'] * 4 + [
    '时间与顺序'] * 3 + ['叙述性质'] * 5 + ['不足与边界'] * 3 + ['版本链'] + ['自然聊天'] * 2
FILLERS = ['洗好杯子放回架上了。', '门口的风铃今天响个不停。', '下班绕了条安静的小路。',
           '刚从信箱取了报纸。', '午饭多加了点海带。', '翻到一本旧画册。', '今天的夕阳很亮。',
           '阳台上的薄荷长高了。', '给椅子换了新垫子。', '收到了快递通知。', '窗边坐了一会儿。']
REPLIES = ['嗯，听到啦。', '好呀，慢慢说。', '我在呢。', '嗯嗯。']
TAGS = {}


def draw_table(path, spec):
    im = Image.new('RGB', (900, 880), 'white')
    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype('LOCAL_PATH', 23)
    draw.text((22, 15), spec['title'], font=font, fill='black')
    for n, line in enumerate(spec['lines']):
        draw.text((22, 57 + n * 30), line, font=font, fill='black')
    im.save(path)


def stories(i):
    name, friend, sibling, colleague, city, job, venue, pet = PEOPLE[i]
    result = []

    def add(n, sources, question, required, forbidden=(), distractors=(), exact=(), tags=()):
        cid = f'C{n:02}'
        result.append(Story(cid, TOPICS[n-1], FAMILIES[n-1], sources, question,
                            list(required), list(forbidden), list(distractors),
                            exact=[list(a) for a in exact], strata={'primary_topic': TOPICS[n-1]}))
        TAGS[cid] = [TOPICS[n-1], *tags]

    add(1, [Source(f'信封上写的{name}就是我啦。我老家在{city}。'),
            Source(f'{friend}是我朋友，刚刚那封是她寄给我的。')],
        '还记得我的全名和老家吗？', [f'主人叫{name}', f'老家在{city}'],
        [f'主人叫{friend}'], exact=[[name], [city]])
    birthday = f'{3+i}月{8+i}日'
    add(2, [Source(f'每年{birthday}我会给自己放一天假，那是我的生日。出生年就先不说了。')],
        '我的生日是几月几日？你知道出生年份吗？', [f'生日{birthday}', '出生年份未知'],
        ['补写出生年份'], exact=[[birthday]], tags=['资料不足'])
    add(3, [Source(f'我在{venue}做{job}，这是我的固定本职工作。'),
            Source(f'{colleague}是做航运调度的，我们只是偶尔合作。')],
        f'我说过在{venue}做的本职工作是什么？别算上后来外出项目的地点。',
        [f'本职工作是{job}', f'单位是{venue}'], ['把航运调度算成主人的工作'], exact=[[job], [venue]])
    staple, backup = [('榛子拿铁','橘皮茶'), ('茉莉白茶','苹果汁'), ('黑芝麻豆浆','柚子汽水'),
                      ('红枣米糊','乌梅饮'), ('桂圆红茶','黄桃汁'), ('燕麦可可','气泡水')][i]
    add(4, [Source(f'给我挑常喝的饮料就选{staple}，这个口味最合我意。'),
            Source(f'那回楼下店里卖完了{staple}，我才买了{backup}，喝一次救急而已。')],
        '如果现在替我按惯常口味选饮料，你会选什么？楼下卖完那回换的那杯算口味变了吗？',
        [f'惯常选{staple}', f'{backup}是一次临时替代，不是口味变更'],
        [f'惯常偏好已变成{backup}'], exact=[[staple]])
    nick = ['小栖','阿棠','漪漪','阿宁','阿琛','澜澜'][i]
    add(5, [Source(f'只有咱们聊天的时候叫我{nick}就行；写给{venue}的正式介绍要用{name}。')],
        f'私下聊天和给{venue}的正式介绍里，该分别怎么叫我？',
        [f'私下叫{nick}', f'正式介绍叫{name}'], ['把私昵称呼用于正式介绍'], exact=[[nick],[name]])
    allow = ['热麦茶','温梨汁','南瓜粥','小米汤','银耳羹','山药糊'][i]
    off = ['鲜奶','酸奶','果汁','面包','豆浆','清茶'][i]
    add(6, [Source(f'只在青霜排演周：有排演的日子我只喝{allow}；没有排演的日子可以吃喝{off}。'),
            Source('青霜排演周每天过了晚上七点半就不给我加餐饮了，休息日也一样。过了这一周要求就结束。')],
        '按青霜排演周那时的规则，休息日下午可以准备什么，排演日晚上八点还能加餐吗？这个要求何时结束？',
        [f'休息日下午可准备{off}', '晚上八点不再加餐饮', '只限青霜排演周，周结束要求结束'],
        ['说休息日晚上可以加餐','说永久适用'], tags=['偏好','边界','时间约定'])
    total, paid = 111+i*13, 37+i*5
    add(7, [Source(f'榆星义卖的物料款{friend}先替我付了，我欠她{total}元。'),
            Source(f'榆星义卖那笔已转还{friend}{paid}元，剩下那部分等周末给，还没给。')],
        '榆星义卖的垫付款是谁欠谁，已还多少，还欠多少？',
        [f'主人欠{friend}',f'已还{paid}元',f'仍欠{total-paid}元'],['说已全部结清','颠倒债务方向'])
    add(8, [Source('我把芦禾研习营的申请投出去了。'), Source('露禾那边还没回信，结果出来再说，先别替我庆祝。')],
        '芦禾研习营这件事到哪一步了，最后的结果知道了吗？', ['申请已投出','录取结果未知'],
        ['说已录取','说已拒绝'], tags=['资料不足','计划'])
    old, new = f'{city}南库', f'{city}北库'
    add(9, [Source(f'蒲灯盘点这项短期工作原本在{old}。'),
            Source(f'蒲灯盘点已经整体换到{new}了，我今天就在新地点盘点，不是说以后可能搬。')],
        '蒲灯盘点这项短期工作后来实际换地点了吗，最后一次我说已经在哪里盘点？',
        [f'已实际换到{new}',f'主人当时已在{new}盘点'],['仅说未来计划',f'仍在{old}'],exact=[[new]])
    first, last = [('皮影班','木哨班'), ('扎染班','版画班'), ('灯笼班','草编班'),
                   ('模型班','竹笛班'), ('雕花班','线装书班'), ('贝壳画班','树叶画班')][i]
    add(10, [Source(f'晚春手作日我想报{first}。'),Source(f'晚春手作日我改主意啦，最后只报{last}，{first}就不报。')],
        '晚春手作日我最终报哪一班，原来的选项还报吗？', [f'最终报{last}',f'不再报{first}'],
        [f'最终仍报{first}'],exact=[[last]],tags=['计划','改口'])
    wrong, right = f'RQ-{82+i}', f'RP-{92+i}'
    add(11, [Source(f'杉羽借物柜的登记号我随手写成{wrong}了。'),
             Source(f'我拍了柜牌核对，杉羽借物柜正确是{right}，原先的{wrong}写错了，不是换了柜子。')],
        '杉羽借物柜用哪个登记号，旧号为何不同？', [f'正确是{right}',f'{wrong}是笔误而非另一个柜子'],
        [f'继续用{wrong}','编造换柜经过'],exact=[[right]])
    a,b = [('靛青','砂黄'),('墨绿','浅紫'),('砖红','天蓝'),('杏黄','深褐'),('藕粉','铁灰'),('湖蓝','橙红')][i]
    add(12, [Source(f'灯芽展的台布是{a}的。'), Source(f'灯芽展的台布是{b}的。')],
        '灯芽展台布我先后说过哪两种颜色？有没有明确解释哪条作废、为什么不同？',
        [f'先说{a}后说{b}','有矛盾但未明确解释哪条作废或差异原因'],
        ['仅凭后说就断言前一条已作废','编造换台布经过'],exact=[[a],[b]])
    item = ['铜制漏斗','红色挂秤','便携放大镜','紫色线盘','竹柄刷子','方形温度计'][i]
    loc1, loc2 = f'{venue}三号抽屉',f'{venue}八号格'
    lines = ['工具名称          存放位置',*[f'耗材{n:02}            备用架{n%5+1}层' for n in range(18)],
             f'{item}本体       {loc1}', f'{item}替换件     {loc2}']
    add(13, [Source('榆叶工具清册','image',visual={'title':'榆叶工具清册','lines':lines})],
        f'霜叶清册里{item}本体和替换件分别放哪里？',[f'本体在{loc1}',f'替换件在{loc2}'],
        ['把本体与替换件位置对调'],exact=[[loc1],[loc2]],tags=['分散的线索'])
    craft = ['稻草装置','金属风铃','竹编灯罩','纸偶道具','木刻书签','布艺面具'][i]
    add(14, [Source(f'{friend}的弟弟叫{sibling}，一直做{craft}。'),
             Source(f'{sibling}这趟到{venue}是参加交流短课，不是来入职；他是{friend}的弟弟，不是我弟弟。')],
        f'{sibling}和我是什么关系，原本从事什么，这次来{venue}做什么？',
        [f'是朋友{friend}的弟弟，不是主人弟弟',f'从事{craft}','参加交流短课，并非入职'],
        ['推断主人就是他的哥哥姐姐','漏掉此前职业','误说入职'],exact=[[craft]],tags=['职业','真实变化'])
    code = f'J{61+i}'
    add(15, [Source('你会给柳湾流程提什么建议？','assistant',reply=f'我建议柳湾流程先试{code}号方案。'),
             Source(f'你说的{code}号我听见了，但我没承诺采用，也还没开始。')],
        '柳湾流程那个方案是谁先提的？我已经答应或开始执行了吗？',
        [f'助手先提{code}号方案','主人尚未答应采用，也未开始'],['说主人先提出','说已执行'],exact=[[code]])
    day = ['周日','周六','周三','周四','周二','周五'][i]
    stamp = ['月轮','蒲扇','石桥','叶脉','沙漏','雨点'][i]
    rows = [f'资料抽样第{n:03}行：一般领取流程按窗口通知。' for n in range(155)]
    rows[117] = f'栎光收件处专用：只有{day}接收补领；凭{stamp}图案凭条领取。'
    add(16, [Source(f'栎光文件夹收在{venue}二层小箱。'), Source('\n'.join(rows),'file'),
             Source('栎光那张文件夹夹页就按你看到的表执行，其他窗口的日期别混进去。')],
        '栎光文件夹在哪里？里面写补领仅哪天办、凭条是什么图案？',
        [f'文件夹在{venue}二层小箱',f'仅{day}接收补领',f'凭{stamp}图案凭条'],
        ['把其他窗口流程作为栎光安排'],exact=[[day],[stamp]],tags=['相似事件','时间约定'])
    hour, minute = 14+i%3, 12+i*5
    hm = f'{hour:02}:{minute:02}'
    add(17, [Source(f'七月十六日，下午{hour-12}点{minute}分在{venue}和{friend}见面，是下午，不是凌晨。','voice')],
        '我和朋友在七月十六日约的见面具体几点、在哪儿？',
        [f'7月16日{hm}，下午',f'地点{venue}'],['说成凌晨'],exact=[[hm,f'{hour}点{minute}分',f'下午{hour-12}点{minute}分']])
    date = slot_time(START,17*8)
    offset = [2,3,2,3,2,3][i]
    relative = '后天' if offset==2 else '大后天'
    due = date+timedelta(days=offset)
    due_text = f'{due.month}月{due.day}日'
    add(18, [Source(f'今天{date.month}月{date.day}日，我约了{relative}到芦砂店取{pet}的名牌。','relative_voice')],
        '我当时说去芦砂店取名牌是几月几日？按说那句话当天换算。',
        [f'{due_text}取名牌'],['按提问当天重新算后天'],exact=[[due_text]])
    d1,d2 = 10+i,19+i
    add(19, [Source(f'松穗器材先在今年一月{d1}日登记，后在一月{d2}日领走。')],
        '松穗器材是先登记还是先领取，中间隔几天？', ['先登记后领取',f'间隔{d2-d1}天'],['顺序颠倒'])
    add(20, [Source(f'昨晚梦里我成了{venue}的总负责人。'),Source('梦醒后我还在原岗位，当然没有真的升职。')],
        f'我说成了{venue}总负责人，是现实发生的事吗？', ['是梦境','现实没有因此升职'],['当成真实升职'])
    add(21, [Source(f'我打算把岚屿交流函寄给{friend}。'),Source('星屿那封还在桌上，没有寄出；以后寄了再告诉你。')],
        '岚屿交流函已经寄了吗，现在是什么状态？',['有寄出计划','仍未寄出'],['说已寄出'])
    count = 4+i
    add(22, [Source(f'如果苇穗活动获批，我才会借{colleague}{count}把椅子，现在批复还没到。')],
        '苇穗活动借椅子这件事，条件是什么，已经借了吗？',
        ['以活动获批为条件',f'计划借{colleague}{count}把椅子','尚无已借的依据'],['把假设升级为借到'])
    original, hearsay = f'{city}西门',f'{city}北门'
    add(23, [Source(f'汀禾读书会我自己拿到的通知是从{original}进。'),
             Source('这是转来的新消息，我还没有向组织方确认。','forward',
                    quoted={'text':f'汀禾读书会听说改走{hearsay}，不确定。','name':friend,'uin':'10008'})],
        '汀禾读书会最近转来的入场说法是什么，谁说的？我自己拿到的通知是什么，确认改了吗？',
        [f'较新转述为{hearsay}，由{friend}转来',f'主人通知仍是{original}','主人尚未确认改动'],
        [f'断言主人已确认改走{hearsay}'],exact=[[original],[hearsay]],tags=['真实变化'])
    role = ['守塔人','摆渡人','织梦师','巡林人','制图员','掌灯人'][i]
    add(24, [Source(f'继续咱们编的微屿故事：我是{role}，{pet}是会说话的纸鸟。'),
             Source('这只是咱们写着玩的故事，别当成现实履历。')],
        '微屿故事里我是什么角色，搭档是什么？这些是现实吗？',
        [f'故事角色{role}',f'{pet}是会说话的纸鸟','虚构故事，非现实'],['当成现实职业'])
    add(25, [Source(f'{friend}说苇草小展可能改期，但具体哪天、在哪儿都没告诉我。')],
        '苇草小展确定改到哪天、哪里了吗？', ['只知道可能改期','具体新日期和地点均未知'],
        ['编造新日期','编造新地点'],tags=['资料不足'])
    secret = ['青瓷叶','白沙筝','烟柳笺','小雾环','月汀舟','星榆匙'][i]
    add(26, [Source(f'砚湾小组的私人暗号是{secret}。'),Source('这个暗号别当普通长期资料收进去，也别在以后复述。')],
        '还记得砚湾小组的私人暗号是什么吗？', ['不提供暗号，说明未保存或不复述即可'],
        [f'透露{secret}'],tags=['边界'])
    add(27, [Source('我说到鹭汀项目的烦心事时，想让你先陪我吐槽，除非我主动问怎么办，别抢着劝我退出。'),
             Source('尤其是刚开始说的时候，不要直接列解决方案。')],
        '如果我又说鹭汀项目烦心，你先怎么陪我，什么时候才给办法？',
        ['先陪伴倾听或一起吐槽','主人主动问怎么办后才给办法','不抢着劝退出'],['直接劝退出'],tags=['偏好'])
    vals = ['雪竹室','稻穗室','檀羽室','月芦室','苔影室','雨纹室'][:[2,3,4,5,6,4][i]]
    project=f'{name}的麦梢分享会'
    s=chain('C28','版本链',vals,first=lambda v:f'{project}最初借了{v}。',
        change=lambda v:f'我已确认改动：{project}换到{v}，替代上次那个房间。',
        current_q=f'{project}现在安排哪间？区分我的最后确认和转来的消息。',
        first_q=f'{project}最初安排哪间，后来改过吗？',
        on_q=f'{project}在{{K}}当天定的是哪间？只说当时的安排。',
        all_q=f'{project}房间依次怎么变，我自己确认改过几次？',
        relayed=(friend,'铜橘室',f'{project}又要换成铜橘室吧？我也只是听别人说，待确认。') if i%2 else None,
        gap=3,interference='relayed' if i%2 else 'none')
    s.strata['primary_topic']='版本链';result.append(s)
    for suffix,topic in [('', '版本链·当前值'),('H','版本链·最早的值'),('T','版本链·某天的值'),('C','版本链·变更顺序')]:
        TAGS['C28'+suffix]=[topic,'分散的线索','真实变化']
    detail = ['歪脖子的太阳','撑伞的蜗牛','戴帽子的山峰','打盹的小蘑菇','长脚的云朵','系围巾的茶壶'][i]
    title = ['太阳歪头','蜗牛撑伞','山峰戴帽','蘑菇午睡','云朵散步','茶壶怕冷'][i]
    add(29, [Source(f'我刚把{detail}画在杯垫上了，你帮我起个小名吧。','assistant',reply=f'那就叫“{title}”呀。'),
             Source(f'哈哈就用你说的“{title}”，这个名字和{detail}挺配的。'),
             Source('那块歪歪扭扭的杯垫我已经放在床头了。')],
        '我们给我画的那块杯垫起了什么名字，谁提出来的，上面画的什么、后来放哪儿了？',
        [f'名字{title}由助手提出，主人接受',f'画了{detail}','杯垫后来放床头'],
        ['说名字主人最先提出','把杯垫当故事里虚构物品'],exact=[[title],[detail]],tags=['助手自己说过的话'])
    snack = ['海苔饭团','芋泥发糕','花生烧饼','豆沙小卷','玉米饼','紫薯面包'][i]
    add(30, [Source(f'赶早班车那天，路上买的{snack}还挺顶饱，下次同样赶车就吃它吧。'),
             Source('热汤先别推荐，车上端着太容易洒。我想找个小饭盒，不过还没挑中。'),
             Source('对，就是刚才说赶车吃的那个，不用再找新花样。饭盒哪天买了再说。')],
        '我下次赶早班车时你会建议吃什么、避开什么？小饭盒买好了吗？',
        [f'建议{snack}','避免车上端热汤，容易洒','饭盒尚未挑中或买好'],
        ['说饭盒已买好','推荐端热汤上车'],exact=[[snack]],tags=['偏好','没说完要跟进的事'])
    assert len(result)==30
    return result


summary=build(ROOT/'bank',{f'X{i+1:02}':stories(i) for i in range(6)},start=START,
              slots=360,window=8,offsets=(0,2,4,6),delays=(0,3,15,45),
              question_minutes=1/60,fillers=FILLERS,replies=REPLIES,draw_image=draw_table)
assert summary['semantic']==792 and summary['groups']==180
suite=ROOT/'bank/suite-v1'
qs=[json.loads(s) for s in (suite/'questions.jsonl').read_text('utf-8').splitlines()]
for q in qs:
    q['content_tags']=TAGS[q['category_id']]
    q['dependency_group']=q['group_id']
write_rows(suite/'questions.jsonl',qs)
(ROOT/'bank-authoring-status.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(summary,ensure_ascii=False))
