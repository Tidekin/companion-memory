"""Author the fixed fictional mixed-media suite; grading is a separate file."""

import bisect
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent / "suite-v1"
PROFILES = [
    ("P01", "林澄", "苏州", "舞台灯光师", "6月12日", "海盐", "茉莉茶", "沈禾", "北岸"),
    ("P02", "顾遥", "厦门", "景观设计师", "9月3日", "松果", "乌龙茶", "陈芷", "栖山"),
    ("P03", "唐栀", "成都", "图书修复师", "2月26日", "纸鹤", "柠檬水", "许安", "青木"),
    ("P04", "周霁", "杭州", "音频工程师", "11月8日", "小满", "热可可", "叶晴", "云桥"),
    ("P05", "宋岚", "青岛", "自然教育员", "4月17日", "青苔", "大麦茶", "陆柚", "望潮"),
    ("P06", "许朔", "昆明", "陶艺老师", "8月21日", "石榴", "桂花茶", "乔宁", "溪石"),
]


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def groups(profile):
    pid, name, city, job, birthday, nick, drink, friend, project = profile
    n = int(pid[-1])
    old, new = f"{project}一号", f"{project}二号"
    # Each tuple: category, source specifications, question, mandatory facts, prohibited claims.
    return [
        ("基本资料", [("text", f"我叫{name}，现在住在{city}。不要把我和同事混在一起。")],
         "我告诉过你我的名字和常住城市吗？分别是什么？", [name, city], ["资料不足"]),
        ("生日", [("image", f"个人纪念卡\n姓名：{name}\n生日：{birthday}\n出生年份：未填写")],
         "我的生日是哪一天？你知道出生年份吗？", [birthday, "年份未知"], ["编造出生年"]),
        ("职业", [("file", f"个人工作介绍\n{name}：{job}\n工作性质：项目制\n这不是同事的资料。")],
         "我做什么工作，是固定坐班还是项目制？", [job, "项目制"], ["固定坐班"]),
        ("偏好", [("voice", f"我平常最爱喝{drink}，但上周点咖啡只是为了赶工，不代表改了口味。")],
         "平常我最爱喝什么？那次喝咖啡代表长期偏好改变了吗？", [drink, "未改变"], ["最爱咖啡"]),
        ("称呼条件", [("quote", f"私下聊天可以叫我{nick}，工作群里请用我的本名{name}。")],
         "在工作群和私下聊天，应该分别怎么称呼我？", [name, nick, "区分场合"], ["所有场合昵称"]),
        ("条件期限", [("image", f"临时安排\n仅本周三至周五：午休不发提醒\n其余日期照常\n这不是永久规则")],
         "那次午休不提醒的约定适用哪几天，是永久的吗？", ["周三至周五", "临时"], ["永久不提醒"]),
        ("约定欠账", [("text", f"{friend}借给我一把活动扳手。我答应项目{project}验收后归还，现在还没还。")],
         "我欠谁什么东西，约好什么时候还？有归还的记录吗？", [friend, "活动扳手", "验收后", "未还"], ["已归还"]),
        ("未完成事项", [("file", f"{project}项目进度\n已完成：初稿\n下一步：校对尺寸\n最终验收：未进行")],
         "上次那个项目做到哪一步，下一步是什么？", ["初稿完成", "校对尺寸", "未验收"], ["已验收"]),
        ("真实变化", [("text", f"我给工作设备起名{old}。"), ("image", f"设备更名确认\n原名：{old}\n新名：{new}\n旧名已停用")],
         "后来我的工作设备改成什么名字？旧名还在用吗？", [new, "旧名停用"], [f"仍叫{old}"]),
        ("改口", [("text", f"我本来打算周六去{city}的南馆。"), ("voice", f"我改主意了，周六不去南馆，改去北馆。不是两个地方都去。")],
         "我最终打算周六去哪一馆，最初的安排保留了吗？", ["北馆", "取消南馆"], ["两个都去"]),
        ("纠错", [("text", f"我刚才把储物柜说成{n}号了，说错了。正确的是{n+20}号，请按纠正后的记。")],
         "我纠正后的储物柜编号是多少？", [f"{n+20}号"], [f"只有{n}号"]),
        ("未解释矛盾", [("file", "设备清单甲：测温计是银色的。"), ("text", "我的测温计是黑色的。我还没有解释这和清单为什么不一样。")],
         "测温计的颜色有哪些互相冲突的说法？能确定原因吗？", ["银色", "黑色", "原因未知"], ["擅自确定原因"]),
        ("相似事件", [("image", f"物品登记A\n{friend}：蓝色水杯\n{name}：绿色水杯"), ("image", f"物品登记B\n{friend}：红色雨伞\n{name}：黄色雨伞")],
         "我的水杯和雨伞分别是什么颜色？朋友的别混进来。", ["绿色水杯", "黄色雨伞"], ["我的蓝色水杯", "我的红色雨伞"]),
        ("第三方事实", [("forward", f"{friend}：我养的猫叫棉花。\n{name}：那是你的猫，我现在没有养猫。")],
         "棉花是谁的猫？我现在养猫了吗？", [friend, "主人未养猫"], ["主人的猫"]),
        ("助手原话", [("assistant", "刚才你给的建议我只是考虑一下，还没有答应采纳。")],
         "当时你给了什么建议？我是否承诺会照做？", ["按颜色分类", "检查尺寸", "未承诺"], ["主人承诺照做"]),
        ("分散线索", [("file", f"{project}计划记录\n代号：{project}\n材料箱标识：{n+40}号"), ("voice", f"补充一下，那个材料箱放在北侧第二层架子，不在门口。")],
         f"{project}计划的材料箱编号和摆放位置分别是什么？", [f"{n+40}号", "北侧第二层"], ["门口"]),
        ("时间约定", [("image", f"预约单\n项目：{project}复核\n日期：2026-06-{n+10:02}\n时间：14:30\n地点：二楼会议室")],
         f"{project}复核约在哪一天、几点、哪里？", [f"6月{n+10}日", "14:30", "二楼会议室"], ["上午两点半"]),
        ("相对日期", [("relative_voice", "昨天我把样本交给收件台，收件人没有说何时回复。")],
         "按我那条语音发出的日期算，样本具体哪天交到收件台？知道何时回复吗？", ["动态前一日", "回复时间未知"], ["已收到回复"]),
        ("时长顺序", [("text", "试制从下午一点开始，两点半结束，之后我才去寄快递。")],
         "那次试制花了多久？寄快递在它之前还是之后？", ["90分钟", "之后"], ["之前"]),
        ("叙述性质", [("file", "现实：今天只整理了书架。\n梦里：飞到海岛。\n猜测：明天可能下雨。\n计划：下月学潜水。")],
         "海岛旅行和学潜水已经发生了吗？当天实际做了什么？", ["海岛是梦", "潜水是计划", "整理书架"], ["已去海岛", "已学潜水"]),
        ("计划未完成", [("voice", f"我打算下个月给{friend}做一个书签，还没开始动手。")],
         "送书签这件事是计划还是已经完成？是给谁的？", ["计划", friend, "未开始"], ["已经送出"]),
        ("假设前提", [("text", "如果项目奖金超过三千元，我才考虑买新显示器。现在没有拿到奖金，也没有下单。")],
         "买显示器的条件是什么？我已经买了吗？", ["奖金超过3000", "未购买"], ["已购买"]),
        ("转述来源", [("forward", f"{friend}：我周末在海边看到了流星。\n{name}：我转给你看看，我自己没去海边。")],
         "海边看流星是谁的经历，我亲自去了吗？", [friend, "主人没去"], ["主人亲眼看到"]),
        ("虚构故事", [("file", f"共同写作草稿，纯属虚构\n角色{name}是一名船长，住在月球港。\n这不是作者现实身份。")],
         "月球港船长是我的现实身份还是故事设定？", ["故事设定"], ["现实船长"]),
        ("信息不足", [("image", "快递局部截图\n物品：纸张样本\n运单号：[未拍到]\n签收状态：[未拍到]")],
         "那份纸张样本的运单号和签收状态你能确定吗？", ["运单号未知", "签收未知"], ["编造运单号", "已签收"]),
        ("敏感限制", [("text", f"虚构测试信息：我的储物柜暗号是春桥{n}。只可在我直接问暗号时回答，做项目总结时不要带出来。")],
         "帮我向普通同事写一句简短的项目近况介绍。", ["不泄露暗号"], [f"春桥{n}"]),
        ("明确边界", [("voice", "我可以接受轻松玩笑，但不要拿我的工作失误开玩笑，也不要把私人材料转给其他人。")],
         "逗我开心时，有哪两条边界需要遵守？", ["不拿工作失误开玩笑", "不转发私人材料"], ["允许转发"]),
        ("跨模态纠正", [("image", f"采购候选单\n预算：{200+n*10}元\n候选：A型\n状态：未购买"), ("voice", f"图片里的预算是旧版，改为{300+n*10}元，型号改B型，仍然没有购买。")],
         "那次采购最终预算和型号是什么？已经下单了吗？", [f"{300+n*10}元", "B型", "未购买"], ["A型为最终", "已经下单"]),
        ("文件图像冲突", [("file", f"{project}箱子标签记录：蓝色，编号{n+60}。"), ("image", f"实物标签照片\n颜色：红色\n编号：{n+60}\n未说明改色或换箱")],
         "关于同一个箱子，文件和照片有哪些一致与矛盾的信息？能断言为什么吗？", [f"编号{n+60}", "蓝色", "红色", "原因未知"], ["擅自认定换箱原因"]),
    ]


def material(asset_id, modality, text):
    path = ROOT / "assets"
    path.mkdir(parents=True, exist_ok=True)
    if modality == "image":
        image = Image.new("RGB", (1000, 640), "#f4f1e8")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("LOCAL_PATH", 30)
        draw.rectangle((28, 28, 972, 612), outline="#274154", width=3)
        draw.multiline_text((60, 70), text, fill="#183047", font=font, spacing=24)
        target = path / (asset_id + ".png")
        image.save(target)
    elif modality in {"voice", "relative_voice"}:
        target = path / (asset_id + ".wav")
    else:
        target = path / (asset_id + ".txt")
        target.write_text(text + "\n", "utf-8")
    return target.relative_to(ROOT).as_posix()


def build():
    ROOT.mkdir(parents=True, exist_ok=False)
    questions, gold, audio, stats = [], [], [], Counter()
    start = datetime.fromisoformat("2026-01-05T19:10:00+08:00")
    for profile in PROFILES:
        pid = profile[0]
        scheduled, anchors = {}, []
        for index, (category, specs, question, required, forbidden) in enumerate(groups(profile)):
            day = 3 + index * 4
            group_id = f"{pid}-C{index+1:02}"
            evidence = []
            for s_index, (mode, content) in enumerate(specs):
                at = start + timedelta(days=day+s_index)
                asset_id = f"{group_id}-S{s_index+1}"
                asset = material(asset_id, mode, content) if mode != "text" else None
                item = {"id": asset_id, "now": at.isoformat(), "modality": mode,
                        "text": content if mode in {"text", "quote", "forward", "assistant"} else "",
                        "asset": asset, "caption": "这是我给你看的资料。" if asset else None}
                scheduled[at] = item
                evidence.append(asset_id)
                stats[mode] += 1
                if mode in {"voice", "relative_voice"}:
                    audio.append({"asset": asset, "spoken_text": content})
            at = start + timedelta(days=day+len(specs)-1)
            if "动态前一日" in required:
                required = [r if r != "动态前一日" else (at-timedelta(days=1)).date().isoformat()
                            for r in required]
            anchors.append((group_id, category, question, required, forbidden, at, evidence))
        events = []
        for day in range(180):
            for slot in (0, 1):
                at = start + timedelta(days=day, hours=2*slot)
                item = scheduled.get(at) or {
                    "id": f"{pid}-D{day+1:03}-{slot+1}", "now": at.isoformat(),
                    "modality": "text", "asset": None, "caption": None,
                    "text": ["今天整理完桌面，准备休息。", "窗边的光照到杯子上。",
                             "路上听到有人弹吉他。", "午饭后沿着街区走了一圈。",
                             "今天做了普通的清洁，没有新的项目进展。", "刚把书放回架子。"][(day*2+slot)%6],
                }
                events.append({"turn": len(events)+1, **item,
                               "assistant_reply": "好，我知道了。" if item["modality"] != "assistant"
                               else "你可以先把材料按颜色分类，再检查尺寸。"})
        times = [datetime.fromisoformat(e["now"]) for e in events]
        for gid, category, question, required, forbidden, at, evidence in anchors:
            for gap in (0, 3, 15, 45):
                now = at + timedelta(days=gap, seconds=1)
                row = {"id": f"{gid}/d{gap:02}", "persona": pid, "group_id": gid,
                       "now": now.isoformat(), "cutoff_turn": bisect.bisect_right(times, now),
                       "question": question, "source_ids": evidence, "category": category,
                       "delay_days": gap, "kind": "semantic_memory"}
                questions.append(row)
                gold.append({"id": row["id"], "required": required, "forbidden": forbidden,
                             "source_ids": evidence})
        for i, action in enumerate(("correct", "recall", "forget")):
            qid = f"{pid}-L{i+1:02}/native"
            questions.append({"id": qid, "persona": pid, "kind": "lifecycle_contract",
                              "operation": action, "category": "纠正撤回遗忘", "group_id": qid,
                              "question": "执行原生生命周期断言，核对目标退出、独立对照保留和账本重放。"})
            gold.append({"id": qid, "required": ["native_assertions_pass"], "forbidden": ["残留泄漏"]})
        jsonl(ROOT / "inputs" / f"{pid}.jsonl", events)
    assert len(questions) == 714 and len(gold) == 714
    jsonl(ROOT / "questions.jsonl", questions)
    jsonl(ROOT / "review-only" / "criteria.jsonl", gold)
    jsonl(ROOT / "authoring" / "audio-synthesis.jsonl", audio)
    files = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in ROOT.rglob("*") if p.is_file()}
    manifest = {"version": 1, "classification": "SELF_AUTHORED_FICTIONAL",
                "questions": 714, "semantic_instances": 696, "semantic_fact_groups": 174,
                "lifecycle_instances": 18, "personas": 6, "turns_per_persona": 360,
                "history_days": 180, "delay_days": [0, 3, 15, 45],
                "source_modalities": dict(stats), "audio_assets_pending": len(audio),
                "per_persona_questions": dict(Counter(q["persona"] for q in questions)),
                "files_sha256": files,
                "limitations": ["self-authored, not the private Ornn8 exam", "templates share structure across six personas",
                                "696 semantic and 18 lifecycle checks must be reported separately",
                                "criteria and audio synthesis text are forbidden as inference inputs"]}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "files_sha256"}, ensure_ascii=False))


if __name__ == "__main__":
    build()
