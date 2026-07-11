"""
迈瑞 (Mindray) 监护仪报警解析库使用示例
=========================================

本文件展示如何使用 app.mindray_alarm 库：
1. 解析单条 HL7 报警消息
2. 从 OBX/AL1 段提取报警信息
3. 评估参数是否越限
4. 将解析结果推送到 WebSocket/数据库

运行: python -m app.mindray_alarm.example
"""

from app.mindray_alarm import (
    MindrayAlarmParser,
    parse_hl7_alarm_message,
    extract_alarm_from_obx,
    evaluate_limit_violation,
    get_alarm_description,
    get_alarm_priority,
    get_normal_range,
)


def demo_single_message_parse():
    """示例1: 解析单条 HL7 报警消息"""
    print("=" * 60)
    print("【示例1】解析完整 HL7 报警消息")
    print("=" * 60)
    
    hl7_message = (
        "MSH|^~\\&|Mindray|BeneVision-001||20240115083000||ORU^R01|MSG0001|P|2.3\r"
        "PID|1||P20240001||Zhang^San||19850101|M\r"
        "OBX|1|NM|149530^心率^ISO||85|bpm|60^100|N|||F\r"
        "OBX|2|NM|196608^心率过高^ISO||125|bpm|60^100|H|||A\r"
        "OBX|3|NM|196610^血氧饱和度过低^ISO||88|%|95^100|L|||A\r"
        "OBX|4|ST|198004^SpO2探头脱落^ISO||FAULT|||||A"
    )
    
    result = parse_hl7_alarm_message(hl7_message, device_ip="192.168.1.100")
    
    print(f"\n设备: {result.device_sn} (IP: 192.168.1.100)")
    print(f"时间: {result.timestamp}")
    print(f"患者: {result.patient_name} (ID: {result.patient_id})")
    print(f"消息类型: {result.message_type}")
    print(f"\n共发现 {len(result.alarms)} 条报警:")
    
    for i, alarm in enumerate(result.alarms, 1):
        print(f"\n  [{i}] {alarm.summary}")
        print(f"      MDC代码: {alarm.mdc_code}")
        print(f"      参数键: {alarm.parameter_key}")
        print(f"      观测值: {alarm.observed_value}{alarm.unit}")
        print(f"      参考范围: {alarm.reference_range}")
        print(f"      越限类型: {alarm.violation_type}")
        print(f"      分类: {alarm.alarm_category}")
        print(f"      处理建议: {alarm.response_suggestion}")


def demo_parser_class():
    """示例2: 使用高级解析器类"""
    print("\n" + "=" * 60)
    print("【示例2】使用 MindrayAlarmParser 高级解析器")
    print("=" * 60)
    
    parser = MindrayAlarmParser()
    
    # 设置自定义报警限（HR: 50-110, SpO2: 92-100）
    parser.set_custom_limit("HR", 50, 110)
    parser.set_custom_limit("SPO2", 92, 100)
    
    # 模拟多条消息流
    messages = [
        "MSH|^~\\&|Mindray|DEV-001||20240115090000||ORU^R01|M1|P|2.3\r"
        "OBX|1|NM|196608^心率过高^ISO||115|bpm|50^110|H|||A\r"
        "OBX|2|NM|197000^心脏停搏^ISO||0||||A",
        
        "MSH|^~\\&|Mindray|DEV-002||20240115090100||ORU^R01|M2|P|2.3\r"
        "OBX|1|ST|198000^ECG电极脱落^ISO||FAULT|||||A\r"
        "OBX|2|NM|196610^血氧低^ISO||90|%|92^100|L|||A",
        
        "MSH|^~\\&|Mindray|DEV-001||20240115090200||ORU^R01|M3|P|2.3\r"
        "OBX|1|NM|197013^ST段抬高^ISO||2.5|mV|-0.1^0.1|A|||A",
    ]
    
    print("\n开始解析消息流...\n")
    for msg in messages:
        result = parser.parse(msg)
        print(f"[消息 {result.message_id}] 设备 {result.device_sn} → "
              f"{len(result.alarms)} 条报警")
        
        # 只关注红色高优先级报警
        high_alarm = parser.get_high_priority_alarms(result)
        for alarm in high_alarm:
            print(f"  ⚠️  红色报警: {alarm.alarm_text_zh} - "
                  f"{alarm.response_suggestion}")
    
    # 统计信息
    print("\n" + "-" * 60)
    stats = parser.get_statistics()
    print(f"解析统计: 共 {stats['total_messages']} 条消息, "
          f"{stats['total_alarms']} 条报警")
    print(f"  红色(1级): {stats['level_1']} | "
          f"黄色(2级): {stats['level_2']} | "
          f"白色(3级): {stats['level_3']}")
    print(f"  生理报警: {stats['physiological']} | "
          f"技术报警: {stats['technical']} | "
          f"心律失常: {stats['arrhythmia']}")


def demo_limit_evaluation():
    """示例3: 评估参数是否越限"""
    print("\n" + "=" * 60)
    print("【示例3】参数越限评估")
    print("=" * 60)
    
    test_cases = [
        ("HR", 55), ("HR", 105), ("HR", 75),
        ("SpO2", 88), ("SpO2", 97),
        ("RR", 32), ("RR", 16),
        ("SYS", 155), ("SYS", 85),
        ("TEMP", 38.5), ("TEMP", 35.8),
    ]
    
    print("\n参数正常范围参考:")
    for key in ["HR", "SPO2", "RR", "SYS", "DIA", "TEMP"]:
        r = get_normal_range(key)
        if r:
            print(f"  {key:6s}: {r[0]:.0f} - {r[1]:.0f} {r[2]}")
    
    print("\n越限评估测试:")
    for param, value in test_cases:
        result = evaluate_limit_violation(param, value)
        status = "✗ 越限" if result["is_violation"] else "✓ 正常"
        marker = f"({result['violation_type']}, +{result['deviation']}%)" if result["is_violation"] else ""
        print(f"  {param:6s} = {value:6.1f} → {status} {marker}")


def demo_code_lookup():
    """示例4: MDC 编码查询"""
    print("\n" + "=" * 60)
    print("【示例4】MDC 编码查询")
    print("=" * 60)
    
    test_codes = ["196608", "197000", "198004", "149530", "197013"]
    
    print("")
    for code in test_codes:
        desc = get_alarm_description(code)
        priority = get_alarm_priority(code)
        print(f"  MDC {code} → {desc} [{priority}]")


if __name__ == "__main__":
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + "迈瑞监护仪报警信息解析库 - 演示程序".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    
    try:
        demo_single_message_parse()
        demo_parser_class()
        demo_limit_evaluation()
        demo_code_lookup()
        
        print("\n" + "=" * 60)
        print("所有演示完成 ✅")
        print("=" * 60)
    except Exception as e:
        print(f"\n演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()