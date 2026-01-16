// create an empty modbus client
const ModbusRTU = require("modbus-serial")
const client = new ModbusRTU();

// open connection to a tcp line
client.connectTCP("10.10.112.5", { port: 10502 });
client.setID(1);

// 监听 debug 事件
client.on("debug", function (data) {
    console.log("Debug:", data);
});

// read the values of 10 registers starting at address 0
// on device number 1. and log the values to the console.
setInterval(function () {
    client.readHoldingRegisters(0, 10, function (err, data) {
        console.log(data.data);
    });
    // 手动打印发送的报文
    console.log("发送的报文:", client._port._buffer);
}, 1000);