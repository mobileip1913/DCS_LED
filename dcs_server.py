import serial
from flask import Flask, render_template_string, jsonify, request
from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext, ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification
import threading
import asyncio
import signal
import time

# 配置参数（根据实际环境调整）
SERIAL_PORT = 'COM3'  # Windows串口（如COM3）或Linux串口（如/dev/ttyUSB0）
BAUDRATE = 9600       # 波特率（与从机设备一致）
STOPBITS = serial.STOPBITS_ONE  # 停止位（1位）
SLAVE_IDS = [1, 2, 3, 4]        # 从机地址（1-4号机组）

# 机组指标定义（每个机组11个指标，与寄存器数量严格同步）
UNIT_METRICS = {
    1: [
        "#1机发电机有功功率", "#1机发电机无功功率", "#1机汽机主蒸汽温度",
        "#1机主蒸汽电动门前压力", "#1机再热器蒸汽温度", "脱硫岛氮氧化物到DCS",
        "脱硫岛粉尘DUST到DCS", "#1机凝汽器真空", "#1机工业抽气总流量",
        "脱硫岛二氧化硫到DCS", "#1机民用供热流量"
    ],
    2: [
        "#2机发电机有功功率", "#2机发电机无功功率", "#2机汽机主蒸汽温度",
        "#2机主蒸汽电动门前压力", "#2机再热器蒸汽温度", "脱硫岛氮氧化物到DCS",
        "脱硫岛粉尘DUST到DCS", "#2机凝汽器真空", "#2机工业抽气总流量",
        "脱硫岛二氧化硫到DCS", "#2机民用供热流量"
    ],
    3: [
        "#3机发电机有功功率", "#3机发电机无功功率", "#3机汽机主蒸汽温度",
        "#3机主蒸汽电动门前压力", "#3机再热器蒸汽温度", "脱硫岛氮氧化物到DCS",
        "脱硫岛粉尘DUST到DCS", "#3机凝汽器真空", "#3机工业抽气总流量",
        "脱硫岛二氧化硫到DCS", "#3机民用供热流量"
    ],
    4: [
        "#4机发电机有功功率", "#4机发电机无功功率", "#4机汽机主蒸汽温度",
        "#4机主蒸汽电动门前压力", "#4机再热器蒸汽温度", "脱硫岛氮氧化物到DCS",
        "脱硫岛粉尘DUST到DCS", "#4机凝汽器真空", "#4机工业抽气总流量",
        "脱硫岛二氧化硫到DCS", "#4机民用供热流量"
    ]
}


class DCSModbusSlave:
    def __init__(self):
        # 初始化从机上下文（每个从机对应11个保持寄存器）
        self.datastore = {}
        for slave_id in SLAVE_IDS:
            # 数据块地址从1开始（对应Modbus地址40001），初始值全0
            block = ModbusSequentialDataBlock(
                address=1,
                values=[0.0] * len(UNIT_METRICS[slave_id])  # 11个寄存器
            )
            # 绑定保持寄存器（HR）到数据块
            self.datastore[slave_id] = ModbusSlaveContext(hr=block)
        
        # 服务器上下文（多从机模式）
        self.context = ModbusServerContext(slaves=self.datastore, single=False)
        
        # 设备标识（可选，用于Modbus主站识别）
        self.identity = ModbusDeviceIdentification(
            info_name={
                'VendorName': 'DCSMonitor',
                'ProductCode': 'DCS01',
                'VendorUrl': 'https://example.com',
                'ProductName': '机组数据Modbus从机',
                'ModelName': 'RTU-4Slave',
                'MajorMinorRevision': '2.0'
            }
        )
        
        self.server = None
        self.loop = None
        self.data_cache = {
            slave_id: {name: 0.0 for name in UNIT_METRICS[slave_id]}  # 缓存指标值（用于Web显示）
            for slave_id in SLAVE_IDS
        }

    async def _start_server_async(self):
        """异步启动Modbus RTU服务器"""
        self.server = await StartSerialServer(
            context=self.context,
            identity=self.identity,
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            stopbits=STOPBITS,
            method='rtu',  # RTU模式（常见工业协议）
            timeout=2.0    # 串口超时时间（秒）
        )
        print(f"✅ Modbus RTU服务器启动成功 | 端口：{SERIAL_PORT} | 从机地址：{SLAVE_IDS}")

    def start(self):
        """启动服务器（在独立线程中运行）"""
        def run_server():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            # Windows下避免事件循环警告
            if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            try:
                self.loop.run_until_complete(self._start_server_async())
                self.loop.run_forever()
            except Exception as e:
                print(f"❌ Modbus服务器异常：{str(e)}")
            finally:
                if self.server:
                    self.server.close()
                self.loop.close()
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

def update_register(self, slave_id: int, index: int, value: float):
    if slave_id not in self.datastore:
        raise ValueError(f"无效从机ID：{slave_id}")
    if not (0 <= index < len(UNIT_METRICS[slave_id])):
        raise IndexError(f"指标索引超出范围（0-{len(UNIT_METRICS[slave_id])-1}）")
    
    addr = 1 + index  
    try:
        print(f"尝试为从机 {slave_id}，索引 {index} 设置值 {value}，寄存器类型为 holdingregister")
        self.datastore[slave_id].setValues('holdingregister', addr, [value])
        self.data_cache[slave_id][UNIT_METRICS[slave_id][index]] = round(value, 2)
        print(f"为从机 {slave_id}，索引 {index} 设置值 {value} 成功")
    except Exception as e:
        print(f"设置寄存器值时出现异常: {e}") 


# 初始化Flask应用
app = Flask(__name__)
slave = DCSModbusSlave()
slave.start()  # 启动Modbus服务器


@app.route('/')
def index():
    """Web监控页面（实时显示机组数据）"""
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DCS机组数据监控</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .card { 
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); 
                transition: transform 0.2s;
                background: white;
                border-radius: 0.5rem;
                padding: 1.5rem;
            }
            .card:hover { transform: translateY(-2px); }
            .metric-value { 
                font-family: monospace;
                font-variant-numeric: tabular-nums;  # 数字对齐
            }
        </style>
    </head>
    <body class="bg-gray-100 p-4">
        <h1 class="text-2xl font-bold text-gray-900 mb-6 text-center">DCS机组实时数据监控</h1>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {% for slave_id in slave.data_cache|sort %}
            <div class="card">
                <h2 class="text-xl font-semibold text-blue-600 mb-4">#{{ slave_id }}机组</h2>
                <div class="space-y-2">
                    {% for name, value in slave.data_cache[slave_id].items() %}
                    <div class="flex justify-between items-center">
                        <span class="text-sm text-gray-600">{{ name }}</span>
                        <span class="text-lg metric-value text-green-700">
                            {{ value|round(2) }}
                        </span>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        </div>
        <div class="text-center mt-6 text-sm text-gray-500">
            最后更新时间：{{ now|strftime('%Y-%m-%d %H:%M:%S') }}
        </div>
    </body>
    </html>
    ''', slave=slave, now=time.time())


@app.route('/api/receive-data', methods=['POST'])
def receive_data():
    """接收发送程序的数据并更新寄存器"""
    try:
        data = request.json
        # 校验必要参数
        if not all(key in data for key in ['slave_id', 'index', 'value']):
            return jsonify({"status": "error", "message": "缺少必要参数：slave_id/index/value"})
        
        slave_id = data['slave_id']
        index = data['index']
        value = data['value']
        
        # 校验参数范围
        if slave_id not in SLAVE_IDS:
            return jsonify({"status": "error", "message": f"slave_id必须为{SLAVE_IDS}中的整数"})
        if not (0 <= index < len(UNIT_METRICS[slave_id])):
            return jsonify({"status": "error", "message": f"index范围应为0-{len(UNIT_METRICS[slave_id])-1}"})
        if not (0.01 <= value <= 200):
            return jsonify({"status": "error", "message": "value必须在0.01-200之间"})
        
        # 更新寄存器
        slave.update_register(slave_id, index, value)
        return jsonify({
            "status": "success",
            "message": f"更新成功：#{slave_id}机 | {UNIT_METRICS[slave_id][index]}",
            "value": round(value, 2)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


def handle_exit(signum, frame):
    """处理程序退出（释放资源）"""
    print("\nℹ️ 接收到退出信号，正在停止服务...")
    # 关闭Modbus服务器（可选）
    if slave.server:
        slave.server.close()
    exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)  # 捕获Ctrl+C退出
    signal.signal(signal.SIGTERM, handle_exit)
    app.run(host='0.0.0.0', port=5000, debug=False)  # 生产环境关闭debug模式