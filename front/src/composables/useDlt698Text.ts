import { useI18n } from "vue-i18n";
/** Protocol-specific copy follows the application's current language. */
export function useDlt698Text() {
  const { locale } = useI18n();
  return (zh: string, en: string) => (locale.value === "en-US" ? en : zh);
}
