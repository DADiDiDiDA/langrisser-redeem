"""
Langrisser (梦幻模拟战) BWIKI 兑换码自动领取脚本

原理：用 Playwright 像真人一样打开 BWIKI 礼品码页面，选择服务器、填入角色 ID，
然后逐个点击状态为“领取”的按钮。由于“领取”走的是动态签名机制，浏览器自动化
比直接 requests 模拟更稳妥。

账号已内置默认值：服务器「热爱无限」、角色 ID「3423789005821014377」。
如需覆盖，仍可用环境变量（非空时优先）：
  GAME_SERVER  游戏区服名称
  GAME_ROLE_ID 角色 ID（游戏内左上角头像处查看）

本地调试（覆盖默认值示例）：
  GAME_SERVER="启源之地" GAME_ROLE_ID="3423789005821014377" python redeem.py
"""

import asyncio
import os

from playwright.async_api import async_playwright

URL = "https://wiki.biligame.com/langrisser/Giftcode"

# 默认值已按你的账号填好；如需覆盖，仍可通过环境变量 / Secrets 设置
# GAME_SERVER 与 GAME_ROLE_ID（非空时优先使用环境变量）。
DEFAULT_SERVER = "热爱无限"
DEFAULT_ROLE_ID = "3423789005821014377"

SERVER = os.environ.get("GAME_SERVER", "").strip() or DEFAULT_SERVER
ROLE_ID = os.environ.get("GAME_ROLE_ID", "").strip() or DEFAULT_ROLE_ID


async def select_server(page):
    """选择服务器，按可见文本做包含匹配（比严格 label 匹配更容错）。"""
    await page.wait_for_selector("select#server", timeout=15000)
    options = await page.query_selector_all("select#server option")
    matched = None
    for opt in options:
        text = (await opt.inner_text()).strip()
        if SERVER in text or text in SERVER:
            matched = opt
            break
    if matched is None:
        raise SystemExit(f"未在服务器下拉框中找到匹配项: {SERVER!r}")
    value = await matched.get_attribute("value")
    await page.select_option("select#server", value=value)
    print(f"已选择服务器: {(await matched.inner_text()).strip()}")


async def main():
    if not SERVER or not ROLE_ID:
        raise SystemExit("请在环境变量 / Secrets 中设置 GAME_SERVER 和 GAME_ROLE_ID")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(URL, wait_until="networkidle")

            await select_server(page)
            await page.fill("input#roleId", ROLE_ID)
            await page.wait_for_timeout(1000)  # 等待页面根据输入刷新兑换码列表

            # 多轮点击：每点一个按钮，页面状态会变，新按钮可能出现
            total = 0
            for attempt in range(3):
                buttons = await page.query_selector_all('button:has-text("领取")')
                if not buttons:
                    print(f"第 {attempt + 1} 轮已无可领取的按钮")
                    break
                print(f"第 {attempt + 1} 轮发现 {len(buttons)} 个可领取的兑换码")
                for btn in buttons:
                    try:
                        await btn.click()
                        await page.wait_for_timeout(2000)  # 等待请求 / 签名完成
                        print("已点击一个领取按钮")
                        total += 1
                    except Exception as e:
                        print(f"点击失败: {e}")
                await page.wait_for_timeout(1500)

            print(f"本次共点击领取 {total} 个兑换码")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
