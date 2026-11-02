"""
钉钉机器人通知脚本（加签方式）

读取 redeem.py 写出的 redeem_result.txt，结合 GitHub 注入的 JOB_STATUS，
向钉钉群机器人发送一条 markdown 消息，汇报本次自动领取的运行结果与领取数量。

环境变量：
  DINGTALK_WEBHOOK  机器人完整 webhook（含 access_token）
  DINGTALK_SECRET   加签密钥（SEC）
  JOB_STATUS        GitHub 注入的 job 状态（success/failure/cancelled）
  RUN_URL           本次运行的链接（可选）
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request

WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "").strip()
SECRET = os.environ.get("DINGTALK_SECRET", "").strip()
JOB_STATUS = os.environ.get("JOB_STATUS", "unknown")
RUN_URL = os.environ.get("RUN_URL", "").strip()

# 读取脚本写出的结果
status = JOB_STATUS
claimed = 0
codes = []
try:
    with open("redeem_result.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("STATUS="):
                status = line.split("=", 1)[1]
            elif line.startswith("CLAIMED="):
                claimed = int((line.split("=", 1)[1] or "0").strip() or 0)
            elif line.startswith("CODE="):
                name = line.split("=", 1)[1].strip()
                if name:
                    codes.append(name)
except FileNotFoundError:
    pass

ok = status == "success"
title = "✅ 梦幻模拟战 兑换码自动领取成功" if ok else "❌ 梦幻模拟战 兑换码自动领取失败"
claimed_text = f"**{claimed} 个**" if ok else "—"

text = (
    f"### 🎮 梦幻模拟战 BWIKI 自动领取\n\n"
    f"- **运行状态**：{'成功 ✅' if ok else '失败 ❌'}\n"
    f"- **本次领取**：{claimed_text} 兑换码\n"
)
# 明细：列出本次领取到的具体兑换码名称（最多 30 条，超出提示总数）
if ok and codes:
    shown = codes[:30]
    detail = "\n".join(f"  - {c}" for c in shown)
    if len(codes) > len(shown):
        detail += f"\n  - …等共 {len(codes)} 个"
    text += f"- **领取明细**：\n{detail}\n"
text += f"- **执行时间**：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
if RUN_URL:
    text += f"- **运行详情**：[点击查看 GitHub Actions 日志]({RUN_URL})\n"

if not WEBHOOK or not SECRET:
    print("未配置 DINGTALK_WEBHOOK / DINGTALK_SECRET，跳过钉钉通知")
    sys.exit(0)

# 加签：timestamp + secret 做 HMAC-SHA256，base64 后 URL 编码
timestamp = str(round(time.time() * 1000))
string_to_sign = f"{timestamp}\n{SECRET}"
hmac_code = hmac.new(
    SECRET.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
).digest()
sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
url = f"{WEBHOOK}&timestamp={timestamp}&sign={sign}"

payload = json.dumps(
    {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
).encode("utf-8")

req = urllib.request.Request(
    url, data=payload, headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print("钉钉响应:", body)
        # 钉钉成功返回 {"errcode":0,"errmsg":"ok"}
        if '"errcode":0' not in body and '"errcode": 0' not in body:
            sys.exit(1)
except Exception as e:
    print("钉钉发送失败:", e)
    sys.exit(1)
