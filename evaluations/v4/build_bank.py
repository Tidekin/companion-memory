"""Round-4 bank: five new personas, 24 stories each, written after the source freeze.

Rules from round 3 applied: every story has its own event/object names (no story can
change another's answer); no message describes something after its own time; answers
that depend on "now" name the reference time; owner's own corrections and relayed
third-party claims are separate stories; near-duplicate distractors sit next to the
facts they resemble; long tables put the needed row past the first screen.
Usage: python build_bank.py   (tools from benchmarks/memory_campaign on sys.path)
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, "LOCAL_PATH")
from authoring import TZ, Source, Story, build  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FONT = "LOCAL_PATH"
START = datetime(2026, 9, 7, tzinfo=TZ)  # a Monday
WEEK = "一二三四五六日"
# name, friend(女), third(男), org, place, venue, pet, friend's brother, owner uin
PEOPLE = [
    ("祁砚", "苏棠", "陆尧", "社区花园", "南岸门", "云杉馆", "米粒", "苏桐"),
    ("闻溪", "程鸢", "许墨", "城北读书会", "东湖口", "青松阁", "布丁", "程野"),
    ("叶知", "沈悦", "顾川", "骑行小队", "西桥头", "白鹭楼", "奶糖", "沈岚"),
    ("方迟", "林夏", "赵野", "摄影社", "北街口", "枫叶堂", "可乐", "林朔"),
    ("夏禾", "唐宁", "周屿", "志愿者中心", "中心广场", "银杏楼", "团子", "唐越"),
]
COUNTS = [(4, 2, 3), (3, 5, 2), (2, 3, 4), (5, 1, 2), (3, 2, 5)]
PRICES = [(18, 26, 9), (35, 12, 48), (22, 15, 30), (16, 40, 7), (28, 19, 11)]
CODES = ["3608", "1275", "4931", "2846", "5713"]
TAILS = ["7742", "0386", "5519", "6203", "1958"]
FILLERS = [
    "今天早上有点雾。", "中午吃了份炒饭。", "下班路上堵车了。", "晚上看了会儿书。", "楼下有人在放音乐。",
    "今天天气挺好的。", "刚倒了杯热水。", "最近睡得还行。", "超市的苹果打折了。", "手机该充电了。",
    "今天走了不少路。", "晚饭做了青菜。", "窗外下了点小雨。", "周末想睡个懒觉。", "办公室有点吵。",
    "刚收拾完桌子。", "今天没什么特别的。", "路上看见一只小狗。", "晚上有点凉了。", "准备早点睡。",
    "今天听了一首老歌。", "刚洗完衣服。", "楼道灯又坏了。", "今天有点累。", "泡了杯茶。",
    "地铁上人不多。", "刚和家里通完电话。", "冰箱里没牛奶了。", "今天看了场球赛。", "外面风挺大。",
]
REPLIES = ["嗯嗯，知道了。", "好呀，早点休息。", "听起来不错。", "辛苦啦。", "哈哈，好的。"]


def day(when):
    return when.date().isoformat()


def stories(i):
    name, friend, third, org, place, venue, pet, brother = PEOPLE[i]
    owner = {"uin": "10001", "name": name}
    s = []

    def add(cid, category, family, sources, question, required, forbidden=(), distractors=()):
        s.append(Story(cid, category, family, sources, question, list(required), list(forbidden),
                       list(distractors)))

    # 基本信息与偏好
    target, shelf, count = ["胶枪", "量角器", "热熔胶棒", "麻绳", "标签打印纸"][i], 3 + i % 3, 6 + i
    items = ["剪刀", "胶带", "记号笔", "订书机", "回形针", "尺子", "便签", "铅笔", "橡皮", "文件夹",
             "夹子", "绳子", "手套", "抹布", "垃圾袋", "电池", "插线板", "螺丝刀", "扳手", "钳子",
             "卷尺", "水桶", "扫把", "簸箕", "海绵", "喷壶", "花盆", "铲子", "种子袋"]
    notes = ["常用", "备用", "待补货", "借出中"]
    rows = [f"{item}{'（大号）' if k >= len(items) else ''}\t{1 + k % 7}\t第{1 + k % 4}层\t{notes[k % 4]}"
            for k, item in enumerate(items * 2)]
    # The needed row sits far past the first screen of the file, next to a look-alike row.
    rows.insert(50, f"{target}\t{count}\t第{shelf}层\t常用")
    rows.insert(51, f"{target}备用件\t1\t第1层\t备用")
    add("T01", "长清单查一项", "基本信息与偏好",
        [Source(f"{org}物资清单\n物品\t数量\t位置\t备注\n" + "\n".join(rows), "file")],
        f"物资清单里{target}有几个、放在第几层？", [f"{target}{count}个", f"放在第{shelf}层"],
        [f"{target}在第1层"])
    add("T02", "相似物品区分", "基本信息与偏好",
        [Source("蓝色雨伞我放在门口鞋柜里了。"), Source("蓝色阳伞在车后备箱，别搞混。")],
        "我的蓝色雨伞放在哪？", ["在门口鞋柜里"], ["雨伞在车后备箱"],
        ["绿色雨伞借给邻居了。"])
    add("T03", "朋友的亲属", "基本信息与偏好",
        [Source(f"{friend}的弟弟叫{brother}，在读大学。"),
         Source(f"{brother}国庆要来我这儿借住几天。")],
        f"{brother}是谁？他要来干什么？",
        [f"{brother}是{friend}的弟弟", "在读大学", "国庆来用户这儿借住几天"],
        [f"{brother}是用户的弟弟"])
    add("T04", "带条件的偏好", "基本信息与偏好",
        [Source("工作日我喝绿茶，周末喝红茶。"), Source("不管哪天，晚上九点以后都别给我泡茶。")],
        "周六下午和周二晚上十点，分别该给我泡什么？", ["周六下午泡红茶", "周二晚上十点不泡茶"],
        ["晚上十点泡绿茶"])
    # 变化纠错与矛盾
    old_line = f"周四前把报名表交给{friend}。"
    add("T05", "主人引用自己旧消息更正", "变化纠错与矛盾",
        [Source(old_line), Source("这里写错了，是周五前交，不是周四。", "quote",
                                  quoted={"text": old_line, **owner})],
        "报名表要在哪天前交？周四为什么不算？", ["周五前交", "周四是主人自己写错后更正的"],
        ["周四前交"])
    add("T06", "主人直接改口", "变化纠错与矛盾",
        [Source("我的工位在三楼东侧。"), Source("不对，上周已经搬到五楼西侧了。")],
        "我现在的工位在哪？以前在哪？", ["现在在五楼西侧", "以前在三楼东侧"],
        ["现在在三楼东侧"])
    add("T07", "转来的第三方通知改时间", "变化纠错与矛盾",
        [Source(f"秋季分享会定在TALK_DAY下午三点，在{venue}。"),
         Source(f"{friend}转来的场馆通知，你看一下。", "forward",
                quoted={"text": "场馆通知：秋季分享会改到TALK_DAY下午四点开始，地点不变。",
                        "name": "场馆通知", "uin": "10005"})],
        "秋季分享会定在几点开始？这个改动是谁说的？",
        ["下午四点开始", "改时间来自转来的场馆通知，不是主人本人说的"], ["仍是下午三点开始"],
        [f"{venue}别的活动时间都没变。"])
    add("T08", "关于主人的传言被主人否认", "来源与归属",
        [Source(f"{third}在群里说的，离谱。", "forward",
                quoted={"text": f"听说{name}要辞职去外地了。", "name": third, "uin": "10006"}),
         Source("我没打算辞职，也不去外地，那是瞎传的。")],
        f"我要辞职去外地吗？那个说法是谁传的？", ["用户没有辞职去外地的打算", f"说法是{third}传的"],
        ["用户要辞职"])
    # 来源与归属
    add("T09", "谁答应了谁", "来源与归属",
        [Source(f"{friend}答应周末帮我修自行车，我说修好请她吃饭。")],
        "谁答应帮谁修车？我答应了她什么？", [f"{friend}答应帮用户修车", "用户答应请她吃饭"],
        [f"用户帮{friend}修车"])
    add("T10", "助手建议被否决", "来源与归属",
        [Source("这周末去哪儿放松好？", "assistant", reply=f"可以去{venue}看那个插画展。"),
         Source("看展算了，我决定去爬山。")],
        "这周末我最后决定去做什么？看展是谁提的？", ["去爬山", "看展是助手提议、被用户否了"],
        ["用户决定去看展"])
    add("T11", "转述链", "来源与归属",
        [Source(f"{friend}转来的话。", "forward",
                quoted={"text": f"{third}跟我说，{place}那家面包店下周关门。", "name": friend,
                        "uin": "10007"}),
         Source("我还没去确认过。")],
        "面包店要关门的消息是谁告诉谁的？我确认过吗？",
        [f"{third}告诉{friend}，{friend}再转告用户", "用户还没确认过"], ["用户亲眼确认过"])
    # 时间与顺序
    add("T12", "下周几换算", "时间与顺序",
        [Source(f"下周五上午十点我要去{venue}面试，按今天说的算。",
                "relative_voice" if i % 2 == 0 else "text")],
        f"我说的那次去{venue}面试，换成公历是哪天几点？", ["NEXT_FRIDAY", "上午10点"],
        ["按提问当天重新计算下周五"])
    add("T13", "跨午夜时长", "时间与顺序",
        [Source("NIGHT_SHIFT_FILE", "file")],
        "那次夜班从几点到几点，一共多长时间？跨天了吗？",
        ["23:20开始", "次日02:05结束", "共2小时45分钟", "跨过了午夜"], ["不到两小时"])
    add("T14", "三件事的先后", "时间与顺序",
        [Source("今天去银行办了张卡。"), Source("今天去理发了。"), Source(f"今天去{venue}还了书。")],
        "办卡、理发、还书分别是哪天？中间那件是什么？",
        ["BANK_DAY办卡", "HAIR_DAY理发", "BOOK_DAY还书", "中间那件是理发"], ["顺序颠倒"],
        ["今天路过银行，没进去。"])
    # 计划假设与梦
    add("T15", "条件计划已触发", "计划假设与梦",
        [Source("如果明天下雨，户外野餐就改到{venue}室内。".replace("{venue}", venue)),
         Source(f"今天真下雨了，户外野餐改在{venue}室内办了。")],
        "户外野餐最后在哪办的？改室内的条件触发了吗？",
        [f"在{venue}室内办", "下雨了，条件已触发"], ["在户外办"])
    add("T16", "计划已完成", "计划假设与梦",
        [Source(f"我打算明天把合同副本寄给{friend}。"),
         Source(f"合同副本已经寄出了，快递单号尾号{TAILS[i]}。")],
        "合同副本寄出了吗？快递单号尾号是多少？", ["已经寄出", f"尾号{TAILS[i]}"], ["还没寄"])
    add("T17", "梦与现实", "计划假设与梦",
        [Source(f"昨晚梦见{pet}走丢了，醒来一看它还在窝里睡觉。", "voice" if i % 2 else "text")],
        f"{pet}真的走丢了吗？", ["走丢只是梦", f"{pet}实际还在窝里"], ["现实中走丢了"])
    # 跨模态
    cups, plates, bowls = COUNTS[i]
    add("T18", "图片计数", "跨模态",
        [Source(f"{org}橱柜照片", "image", visual={"type": "layout", "title": f"{org}橱柜",
                                                   "labels": ["杯子", "盘子", "碗"],
                                                   "counts": [cups, plates, bowls]})],
        "橱柜照片里杯子、盘子、碗各有几个？", [f"杯子{cups}个", f"盘子{plates}个", f"碗{bowls}个"],
        ["数量与图不符"])
    tape, note, box = PRICES[i]
    add("T19", "图片价签被文字更正", "跨模态",
        [Source(f"{org}采购价签照片", "image", visual={"type": "tags", "title": f"{org}采购价签",
                                                      "items": [("胶带", tape), ("便签本", note),
                                                                ("收纳盒", box)]}),
         Source(f"胶带那张价签印错了，实际是{tape + 5}元。")],
        "胶带实际多少钱？价签上印的是多少？", [f"实际{tape + 5}元", f"价签上印的是{tape}元"],
        [f"实际是{tape}元"])
    floor = 2 + i % 4
    add("T20", "语音里的数字", "跨模态",
        [Source(f"我家门牌号是{' '.join(CODES[i])}号，在{floor}单元。", "voice")],
        "我家门牌号和单元是多少？", [f"门牌号{CODES[i]}", f"{floor}单元"], ["编造其他门牌号"])
    surname = name[0]
    add("T21", "表格里找本人", "跨模态",
        [Source(f"排班表上按我的名字{name}找，别看错成{surname}晴。"),
         Source(f"{org}排班表\n日期\t上午\t下午\n周一\t{third}\t{surname}晴\n周三\t{name}\t{friend}\n"
                f"周五\t{surname}晴\t{name}\n周日\t{friend}\t{third}", "file")],
        "排班表里我排在哪两天的哪个时段？周一下午是谁？",
        ["周三上午", "周五下午", f"周一下午是{surname}晴"], ["用户排了周一"])
    # 未知与隐私
    add("T22", "只知道一部分", "未知与隐私",
        [Source(f"{friend}的生日在十二月，具体哪天我也不记得了。")],
        f"{friend}的生日是哪天？", ["具体日期未知", "只知道在十二月"], ["编造具体日期"])
    add("T23", "从未提过的信息", "未知与隐私",
        [Source(f"{third}是新来的{org}志愿者。")],
        f"{third}的手机号是多少？", ["没有记录，不知道"], ["编造手机号"])
    # 多跳
    start = 14 + i % 4
    when_day, other = WEEK[i % 5], WEEK[(i + 2) % 5]
    add("T24", "三跳线索", "多跳线索",
        [Source(f"相机三脚架锁在{venue}的7号柜。"), Source(f"7号柜的钥匙在{friend}手上。"),
         Source(f"{org}值守表\n人\t时间\t地点\n{third}\t周{other} 09:00-11:00\t{venue}\n"
                f"{friend}\t周{when_day} {start}:00-{start + 2}:00\t{place}\n"
                f"{surname}晴\t周日 10:00-12:00\t{venue}", "file")],
        "我想取相机三脚架，要找谁拿钥匙、什么时候、去哪找她？",
        [friend, f"周{when_day}", f"{start}:00-{start + 2}:00", place], [f"找{third}"],
        [f"8号柜的钥匙在{third}那里。"])
    return s


def resolve(persona_stories, start):
    """Fill time-dependent text and answers from each source's actual send time."""
    base = {story.category_id: 2 * (5 + 5 * k) for k, story in enumerate(persona_stories, 1)}

    def when(cid, j):
        offsets = (0, 3, 5, 7)
        slot = base[cid] + offsets[j]
        return start + timedelta(days=slot // 2, hours=9 if slot % 2 == 0 else 20,
                                 minutes=20 if slot % 2 == 0 else 0)

    for story in persona_stories:
        cid = story.category_id
        if cid == "T12":
            said = when(cid, 0)
            friday = said - timedelta(days=said.weekday()) + timedelta(days=11)
            story.required = [day(friday) if r == "NEXT_FRIDAY" else r for r in story.required]
        if cid == "T13":
            end = when(cid, 0)
            night = end - timedelta(days=1)
            story.sources[0].text = (f"夜班记录\n开始\t{day(night)} 23:20\n结束\t{day(end)} 02:05\n"
                                     "备注\t交接完成")
        if cid == "T14":
            story.required = [r.replace("BANK_DAY", day(when(cid, 0)) + " ")
                              .replace("HAIR_DAY", day(when(cid, 1)) + " ")
                              .replace("BOOK_DAY", day(when(cid, 2)) + " ") for r in story.required]
        if cid == "T07":
            talk = day(when(cid, 0) + timedelta(days=10))
            story.sources[0].text = story.sources[0].text.replace("TALK_DAY", talk)
            story.sources[1].quoted["text"] = story.sources[1].quoted["text"].replace("TALK_DAY", talk)
        if cid == "T15":
            # "Tomorrow" in the plan is exactly the day the outcome message is sent.
            assert when(cid, 1).date() == when(cid, 0).date() + timedelta(days=1)
        if cid == "T16":
            assert when(cid, 1).date() >= when(cid, 0).date() + timedelta(days=1)
    return persona_stories


def draw_image(path, visual):
    image = Image.new("RGB", (1050, 720), "#f6f6f2")
    d = ImageDraw.Draw(image)
    big, normal, small = (ImageFont.truetype(FONT, size) for size in (31, 27, 19))
    d.text((40, 25), visual["title"], fill="#2b2b2b", font=big)
    if visual["type"] == "tags":
        for index, (item, price) in enumerate(visual["items"]):
            x = 60 + index * 330
            d.rounded_rectangle((x, 200, x + 280, 460), radius=20, fill="#fff7d6",
                                outline="#8a6d1d", width=4)
            d.text((x + 30, 250), item, fill="#2b2b2b", font=normal)
            d.text((x + 30, 340), f"¥{price}", fill="#b0361f", font=ImageFont.truetype(FONT, 54))
        d.text((40, 670), "价签上的数字为单价（元）。", fill="#666666", font=small)
    else:
        d.line((45, 130, 1000, 130), fill="#555555", width=3)
        d.line((525, 130, 525, 650), fill="#cccccc", width=3)
        d.line((45, 400, 1000, 400), fill="#cccccc", width=3)
        centers = [(250, 250), (740, 250), (525, 510)]
        for index, (label, count, center) in enumerate(zip(visual["labels"], visual["counts"],
                                                           centers, strict=True)):
            for j in range(count):
                x, y = center[0] - (count - 1) * 47 + j * 94, center[1]
                if index == 0:
                    d.rectangle((x - 30, y - 30, x + 30, y + 30), fill="#6b8eb5",
                                outline="#2f4f6f", width=3)
                elif index == 1:
                    d.ellipse((x - 34, y - 30, x + 34, y + 30), fill="#c9a96e",
                              outline="#6e5a35", width=3)
                else:
                    d.polygon([(x, y - 36), (x - 30, y + 30), (x + 30, y + 30)], fill="#e9d36b",
                              outline="#7a6a1d", width=3)
            d.text((center[0] - len(label) * 13, center[1] + 60), label, fill="#2b2b2b",
                   font=normal)
        d.text((40, 670), "数量以图中实际图形个数为准。", fill="#666666", font=small)
    image.save(path)


def main():
    personas = {f"U{i + 1:02}": resolve(stories(i), START) for i in range(len(PEOPLE))}
    summary = build(ROOT / "bank", personas, start=START, fillers=FILLERS, replies=REPLIES,
                    draw_image=draw_image)
    (ROOT / "bank-authoring-status.json").write_text(
        json.dumps({"status": "AUTHORED_PENDING_AUDIO", **summary}, ensure_ascii=False, indent=2),
        "utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
