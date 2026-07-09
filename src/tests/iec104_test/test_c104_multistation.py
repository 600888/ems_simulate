"""
测试 c104 库对多 Station 和相同 IOA 的处理
"""

import c104


def test_c104_multistation():
    """测试 c104 对多个 Station + 相同 IOA 的支持"""

    # 1. 创建 Server，添加两个 Station
    server = c104.Server(ip="0.0.0.0", port=2405)
    s1 = server.add_station(common_address=1)
    s2 = server.add_station(common_address=2)

    # 2. 在两个 Station 上创建相同的 IOA
    p1 = s1.add_point(io_address=100, type=c104.Type.M_ME_NC_1, report_ms=1000)
    p2 = s2.add_point(io_address=100, type=c104.Type.M_ME_NC_1, report_ms=1000)

    print("=== 测试1: Point 对象独立性 ===")
    print(f"p1: {p1}, id={id(p1)}")
    print(f"p2: {p2}, id={id(p2)}")
    print(f"p1 is p2: {p1 is p2}")

    # 3. 通过 get_point 获取
    g1 = s1.get_point(io_address=100)
    g2 = s2.get_point(io_address=100)
    print("\n=== 测试2: get_point 返回结果 ===")
    print(f"g1 (s1.get_point): {g1}, id={id(g1)}")
    print(f"g2 (s2.get_point): {g2}, id={id(g2)}")
    print(f"g1 is p1: {g1 is p1}")
    print(f"g2 is p2: {g2 is p2}")

    # 4. 测试值独立性
    print("\n=== 测试3: 值独立性 ===")
    p1.value = 50.0
    print("设置 p1.value = 50.0")
    print(f"  p1.value = {p1.value}")
    print(f"  p2.value = {p2.value}")

    p2.value = 100.0
    print("设置 p2.value = 100.0")
    print(f"  p1.value = {p1.value}")
    print(f"  p2.value = {p2.value}")

    # 5. 通过 get_point 再读
    g1_val = float(s1.get_point(io_address=100).value)
    g2_val = float(s2.get_point(io_address=100).value)
    print("\n=== 测试4: get_point 返回值 ===")
    print(f"s1.get_point(100).value = {g1_val}")
    print(f"s2.get_point(100).value = {g2_val}")

    # 6. 通过 Server 全局访问
    print("\n=== 测试5: 验证结论 ===")
    if p1 is p2:
        print("结论: p1 is p2 → 不同 Station 的相同 IOA 返回同一个 Point 对象")
        print("      c104 不支持多 Station 重叠 IOA！")
    elif g1_val == g2_val:
        print("结论: 值相同 → 虽然对象不同但值共享")
    else:
        print("结论: 对象独立且值独立 → c104 正确处理多 Station")
        print(f"      s1[100]={g1_val}, s2[100]={g2_val}")

    server.stop()


if __name__ == "__main__":
    test_c104_multistation()
