"""Export the measured score summary with ordinary plotting tools."""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR'] = str(BASE/'.cache/matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


def main():
    s = json.loads((BASE/'result-summary.json').read_text('utf-8'))
    font = FontProperties(fname='LOCAL_PATH')
    plt.rcParams['font.family'] = font.get_name()
    plt.rcParams['axes.unicode_minus'] = False
    colors = {'native': '#285be4', 'reference': '#008594'}
    labels = {'native': 'Companion Core', 'reference': 'Qwen RAG 对照'}
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 8.5), gridspec_kw={'height_ratios': [1, 1.7]})
    fig.patch.set_facecolor('#f3f6fa')
    fig.suptitle('同一批自编题，记忆表现如何？', x=.10, y=.96, ha='left',
                 fontsize=23, fontweight='bold', fontproperties=font, color='#19324b')
    fig.text(.10, .905, '6 个虚构人物 · 696 道问答 · PNG 图卡 / WAV 语音 / TXT 文件输入',
             fontproperties=font, fontsize=11, color='#5c7185')
    ax = axes[0]
    for y, system in enumerate(['reference', 'native']):
        r = s['semantic'][system]
        ax.barh(y, 100, color='#e0e8f1', height=.34)
        ax.barh(y, r['pass_rate_all']*100, color=colors[system], height=.34)
        ax.text(101.5, y, f"{r['passed']}/696\n{r['pass_rate_all']:.1%}", va='center',
                color=colors[system], fontsize=13, fontweight='bold')
    ax.set_yticks([0, 1], [labels['reference'], labels['native']], fontproperties=font)
    ax.invert_yaxis(); ax.set_xlim(0, 117); ax.set_xticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.set_title('整题通过数 / 全部 696 题', loc='left', fontproperties=font, fontsize=12, pad=14)
    ax = axes[1]
    for system in ['reference', 'native']:
        values = [s['pivots']['delay_days'][str(d)][system]['pass_rate_all']*100 for d in [0, 3, 15, 45]]
        ax.plot(range(4), values, marker='o', linewidth=2.5, color=colors[system], label=labels[system])
        for x, value in enumerate(values):
            ax.annotate(f'{value:.1f}%', (x, value), xytext=(0, 9 if system=='reference' else -17),
                        textcoords='offset points', ha='center', color=colors[system], fontsize=11)
    ax.set_ylim(0, 110); ax.set_yticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.set_xticks(range(4), ['当天', '3 天', '15 天', '45 天'], fontproperties=font)
    ax.set_title('距相关证据最后一次出现的时间', loc='left', fontproperties=font, fontsize=12, pad=12)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.13), frameon=False, ncol=2, prop=font)
    for ax in axes:
        ax.set_facecolor('#f3f6fa')
        ax.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
        ax.tick_params(length=0, colors='#526b82')
        ax.grid(axis='y' if ax is axes[1] else 'x', color='#d9e2ec', linewidth=.7)
        ax.set_axisbelow(True)
    fig.text(.10, .087, '另测原生纠正 / 撤回 / 遗忘：18/18 通过，单独统计。', fontproperties=font, fontsize=10, color='#19324b')
    fig.text(.10, .057, '自编语料、模板相关、同系列模型判卷；仅反映固定版本与配置。', fontproperties=font, fontsize=9, color='#5c7185')
    fig.text(.10, .032, '原图正式私有 714 题未公开，不能将两轮成绩直接排名。', fontproperties=font, fontsize=9, color='#5c7185')
    fig.subplots_adjust(left=.25, right=.85, top=.83, bottom=.19, hspace=.48)
    fig.savefig(BASE/'memory-summary.png', dpi=180)
    fig.savefig(BASE/'memory-summary.svg')
    plt.close(fig)


if __name__ == '__main__':
    main()
