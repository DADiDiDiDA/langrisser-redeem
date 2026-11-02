"""
Langrisser (梦幻模拟战) BWIKI 兑换码自动领取脚本

原理：用 Playwright 像真人一样打开 BWIKI 礼品码页面，选择服务器、填入角色 ID，
然后逐个点击状态为「领取 / 仅领取」的按钮。由于「领取」走的是动态签名机制，
浏览器自动化比直接 requests 模拟更稳妥。

页面真实结构（已实测）：
  - 服务器：点 #Server 打开 #ServerModal 弹窗，按大区切 tab，再点
    span.ServerName（文本含服务器名，如「热爱无限」）。
  - 角色 ID：输入框 #roleid（注意是小写 id）。
  - 领取按钮：span.get（可领，文本「领取」）；已领/过期为 span.got，不会被选中，
    因此按 class 选取可避免重复点击。

服务器与角色 ID 通过环境变量提供（在 GitHub Secrets 中配置 GAME_SERVER / GAME_ROLE_ID，
或本地调试时导出）：
  GAME_SERVER  游戏区服/子服务器名称（如「热爱无限」）
  GAME_ROLE_ID 角色 ID（游戏内左上角头像处查看）

本地调试示例：
  GAME_SERVER="热爱无限" GAME_ROLE_ID="3423789005821014377" python redeem.py
"""

import asyncio
import os
import traceback

from playwright.async_api import async_playwright

URL = "https://wiki.biligame.com/langrisser/Giftcode"

# 服务器与角色 ID 必须从环境变量读取（GitHub Secrets：GAME_SERVER / GAME_ROLE_ID）
SERVER = os.environ.get("GAME_SERVER", "").strip()
ROLE_ID = os.environ.get("GAME_ROLE_ID", "").strip()

# 运行结果写入此文件，供钉钉通知步骤读取
RESULT_FILE = "redeem_result.txt"


async def select_server(page, server_name):
    """打开服务器弹窗，切到大区 tab 直到目标服务器可见并点击。"""
    await page.click("#Server")
    await page.wait_for_selector("#ServerModal", state="visible", timeout=10000)
    await page.wait_for_timeout(500)

    tabs = await page.query_selector_all(".ServerListTab li")
    target = None
    for tab in tabs:
        await tab.click()
        await page.wait_for_timeout(400)
        candidates = await page.query_selector_all("span.ServerName")
        for c in candidates:
            txt = (await c.inner_text()).strip()
            if server_name in txt and await c.is_visible():
                target = c
                break
        if target:
            break

    if target is None:
        raise SystemExit(f"未在服务器列表中找到匹配项: {server_name!r}")
    await target.click()
    await page.wait_for_timeout(1000)  # 等待弹窗关闭、列表刷新
    print(f"已选择服务器: {server_name}")


async def main():
    if not SERVER or not ROLE_ID:
        raise SystemExit("请在环境变量 / GitHub Secrets 中设置 GAME_SERVER 和 GAME_ROLE_ID")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        try:
            await page.goto(URL, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            await select_server(page, SERVER)
            await page.fill("#roleid", ROLE_ID)
            await page.wait_for_timeout(2000)  # 等待兑换码列表按服务器+角色加载

            # 多轮点击：每点一个按钮页面会更新，可能冒出新的可领取项
            total = 0
            for attempt in range(4):
                # 领取按钮真实 class 为 .get（可领）；已领/过期为 .got，不会被选中
                buttons = await page.query_selector_all("span.get, span.get-new, span.get-only")
                if not buttons:
                    print(f"第 {attempt + 1} 轮已无可领取的按钮")
                    break
                print(f"第 {attempt + 1} 轮发现 {len(buttons)} 个可领取项")
                for btn in buttons:
                    try:
                        label = (await btn.inner_text()).strip()
                        await btn.click()
                        await page.wait_for_timeout(2500)  # 等待 AJAX 领取完成
                        print(f"已点击: {label}")
                        total += 1
                    except Exception as e:
                        print(f"点击失败 ({label}): {e}")
                await page.wait_for_timeout(1500)

            print(f"本次共点击领取 {total} 个兑换码")
            _write_result("success", total)
        except Exception:
            _write_result("failed", 0)
            # 打印完整堆栈，方便在 GitHub Actions 日志里定位问题
            traceback.print_exc()
            raise
        finally:
            await browser.close()


def _write_result(status, claimed):
    """把运行结果写入文件，供通知步骤读取。"""
    try:
        with open(RESULT_FILE, "w", encoding="utf-8") as f:
            f.write(f"STATUS={status}\nCLAIMED={claimed}\n")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
