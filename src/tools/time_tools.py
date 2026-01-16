import time
from builtins import str
from datetime import datetime, timedelta


class TimeTools:
    @staticmethod
    def getNowTime() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # 获取当前时间的毫秒数
    @staticmethod
    def getDaySeconds(time_str: str) -> int:
        time_array = time.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        time_stamp = int(time.mktime(time_array))
        return time_stamp

    # 获取当天日期时间
    @staticmethod
    def getTodayDateTime() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # 获取明天日期时间
    @staticmethod
    def getTomorrowDateTime() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 86400))

    # 获取当天零点时间
    @staticmethod
    def getTodayMidNightTime() -> str:
        current_date = datetime.strptime(TimeTools.getNowTime(), "%Y-%m-%d %H:%M:%S").date()
        today_midnight = datetime.combine(current_date, datetime.min.time())
        return today_midnight.strftime("%Y-%m-%d %H:%M:%S")

    # 获取传入参数明天零点的时间
    @staticmethod
    def getTomorrowDateTimeByParam(time_para: str) -> str:
        current_date = datetime.strptime(time_para, "%Y-%m-%d %H:%M:%S").date()
        tomorrow_date = current_date + timedelta(days=1)
        tomorrow_midnight = datetime.combine(tomorrow_date, datetime.min.time())
        return tomorrow_midnight.strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    str = "2021-01-01 03:00:00"
    print(TimeTools.getDaySeconds("2021-01-01 00:00:00"))
    print(TimeTools.getTomorrowDateTimeByParam(str))
    print(TimeTools.getDaySeconds(TimeTools.getTodayDateTime()))
    print(TimeTools.getTodayMidNightTime())
