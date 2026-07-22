import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import i18n from "./i18n";
import "element-plus/es/components/message-box/style/css";
import "@/styles/index.scss";
import DecimalDirective from "@/directives/decimalDirective";

// 如果您正在使用CDN引入，请删除下面一行。
const app = createApp(App);
app.use(DecimalDirective);
app.use(router);
app.use(i18n);

app.mount("#app");
