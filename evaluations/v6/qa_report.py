"""Local report browser QA using the repository's existing Playwright dependency."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/playwright'
for name in ('TEMP', 'TMP'):
    destination = ROOT / '.cache' / name.lower()
    destination.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(destination)
from playwright.sync_api import sync_playwright


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        executables = [Path('LOCAL_PATH Files/Google/Chrome/Application/chrome.exe'),
                       Path('LOCAL_PATH Files (x86)/Microsoft/Edge/Application/msedge.exe'),
                       Path('LOCAL_PATH Files/Microsoft/Edge/Application/msedge.exe')]
        executable = next((p for p in executables if p.is_file()), None)
        assert executable, 'No existing Chromium browser; do not silently install a new dependency'
        browser = playwright.chromium.launch(executable_path=str(executable), headless=True)
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto((ROOT / 'memory-report.html').as_uri(), wait_until='load')
            page.locator('figure img').last.wait_for(state='attached')
            desktop = page.evaluate('''() => ({
                question_details: document.querySelectorAll('details.q').length,
                answer_cards: document.querySelectorAll('.answers .answer').length,
                images_loaded: [...document.images].filter(x=>x.complete&&x.naturalWidth>0).length,
                broken_images: [...document.images].filter(x=>!x.complete||x.naturalWidth===0).length,
                desktop_horizontal_overflow: document.documentElement.scrollWidth>innerWidth
            })''')
            page.screenshot(path=str(OUT / 'report-desktop.png'))
            page.locator('.analysis').screenshot(path=str(OUT / 'report-analysis.png'))
            first = page.locator('details.q').first
            first.locator('summary').click()
            assert first.get_attribute('open') is not None
            first.screenshot(path=str(OUT / 'report-question.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUT / 'report-mobile.png'))
            first.screenshot(path=str(OUT / 'report-question-mobile.png'))
            mobile_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            qa = {**desktop, 'mobile_horizontal_overflow': mobile_overflow,
                  'at': datetime.now(UTC).isoformat(), 'script_errors': errors,
                  'detail_open_test': True, 'desktop_viewport': [1280, 900],
                  'mobile_viewport': [390, 844], 'executable': str(executable),
                  'method': 'Existing Playwright and Chromium; local file only; browser closed',
                  'scope': 'Local report verification; no publication or production operation'}
            assert qa['question_details'] == 792 and qa['answer_cards'] == 3168
            assert qa['images_loaded'] == 8 and qa['broken_images'] == 0
            assert not qa['desktop_horizontal_overflow'] and not mobile_overflow and not errors
            (OUT / 'qa.json').write_text(json.dumps(qa, indent=2) + '\n', 'utf-8')
            print(json.dumps(qa))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
