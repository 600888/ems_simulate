def process_hex_address(address: str) -> str:
    """处理地址格式，支持十六进制和十进制输入

    Args:
        address: 地址字符串，可以是 "0x0000" 格式或纯数字 "0", "100"

    Returns:
        格式化后的4位十六进制地址，如 "0x0000"
    """
    address = str(address).strip()

    # 检查地址是否以'0x'开头
    if address.startswith("0x") or address.startswith("0X"):
        # 去掉'0x'前缀
        hex_digits = address[2:]
        # 计算需要补齐的零的个数
        padding_zeros = 4 - len(hex_digits)
        # 如果需要补齐，则在前面添加相应数量的零
        if padding_zeros > 0:
            hex_digits = "0" * padding_zeros + hex_digits
        return "0x" + hex_digits.upper()
    else:
        # 尝试作为十进制数字处理
        try:
            decimal_value = int(address)
            return "0x" + format(decimal_value, "04X")
        except ValueError:
            # 如果无法解析，抛出异常
            raise ValueError(f"{address}, Invalid address format. Should be '0x' hex or decimal number.") from None


def decimal_to_hex(decimal_number: int, length=4) -> str:
    # 首先转换为十六进制字符串
    hex_str = hex(decimal_number)[2:]  # 去掉'0x'前缀
    # 转换为全大写
    hex_str = hex_str.upper()
    # 确保十六进制字符串至少为length位数（不包括'0x'）
    hex_str = hex_str.zfill(length)  # 使用zfill()方法添加前导零
    # 添加'0x'前缀
    formatted_hex_str = "0x" + hex_str
    return formatted_hex_str


def transform(hex_str: str) -> str:
    """
    将十六进制字符串按字节逆序，并智能处理0x前缀

    Args:
        hex_str: 输入的十六进制字符串，可包含空格和0x前缀

    Returns:
        按字节逆序后的十六进制字符串，统一添加0x前缀
    """
    # 1. 移除空格
    clean_str = hex_str.replace(" ", "")

    # 2. 智能识别并去除0x前缀
    if clean_str.startswith("0x") or clean_str.startswith("0X"):
        clean_str = clean_str[2:]  # 去除0x前缀[2,3](@ref)

    # 3. 确保长度为偶数（补零处理）
    if len(clean_str) % 2 != 0:
        clean_str = "0" + clean_str  # 前导补零[5](@ref)

    # 4. 字节逆序（核心逻辑）
    reversed_hex = "".join([clean_str[i : i + 2] for i in range(len(clean_str) - 2, -2, -2)])

    # 5. 统一添加0x前缀返回
    return "0x" + reversed_hex
