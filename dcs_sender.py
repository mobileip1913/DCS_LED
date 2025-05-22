import requests
import time

SERVER_URL = "http://localhost:5000"
SLAVE_ID = 1  # 只测试一个从机
METRIC_INDEX = 0  # 只测试一个指标

def send_data():
    value = 10.0  # 固定测试值
    payload = {
        "slave_id": SLAVE_ID,
        "index": METRIC_INDEX,
        "value": value
    }
    while True:
        try:
            response = requests.post(
                f"{SERVER_URL}/api/receive-data",
                json=payload,
                timeout=3
            )
            result = response.json()
            if result["status"] == "success":
                print(f"发送成功：{result['message']} | 值：{value}")
            else:
                print(f"发送失败：{result['message']}")
        except requests.exceptions.ConnectionError:
            print(f"错误：无法连接到服务器 {SERVER_URL}（请检查服务器是否启动）")
        except requests.exceptions.Timeout:
            print(f"错误：请求超时（服务器无响应）")
        except Exception as e:
            print(f"未知错误：{str(e)}")
        time.sleep(1)

if __name__ == "__main__":
    print("ℹ️ 模拟数据发送程序启动...")
    print(f"ℹ️ 目标服务器：{SERVER_URL}")
    print("ℹ️ 按 Ctrl+C 停止发送")
    send_data()