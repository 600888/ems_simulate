// src/directives/decimalDirective.ts
export default {
    install: (app: any) => {
        app.directive('decimal', {
            mounted(el: any, binding: any) {
                const input = el.querySelector('input') || el;
                const decimalDigits = binding.value || 2;

                const onInput = () => {
                    let val = input.value;
                    val = val
                        .replace(/[^\d.-]/g, '')
                        .replace(/(\..*)\./g, '$1')
                        .replace(/(\-.*)\-/g, '$1');
                    input.value = val;
                };

                const onBlur = () => {
                    let val = input.value;
                    if (val.includes('.')) {
                        const parts = val.split('.');
                        input.value = `${parts[0]}.${parts[1].slice(0, decimalDigits)}`;
                    }
                };

                input.addEventListener('input', onInput);
                input.addEventListener('blur', onBlur);
            }
        });
    }
}