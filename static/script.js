// script.js - máscaras e contador de respostas do formulário de candidatura
(function () {
    var form = document.getElementById('formulario');
    if (!form) return;

    function soDigitos(valor) {
        return valor.replace(/\D/g, '');
    }

    // ---------- Máscara de CPF: 000.000.000-00 ----------
    var cpf = document.getElementById('cpf');
    if (cpf) {
        cpf.addEventListener('input', function () {
            var d = soDigitos(cpf.value).slice(0, 11);
            d = d.replace(/(\d{3})(\d)/, '$1.$2')
                 .replace(/(\d{3})(\d)/, '$1.$2')
                 .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
            cpf.value = d;
        });
    }

    // ---------- Máscara de telefone: (00) 00000-0000 ----------
    var telefone = document.getElementById('telefone');
    if (telefone) {
        telefone.addEventListener('input', function () {
            var d = soDigitos(telefone.value).slice(0, 11);
            if (d.length > 10) {
                d = d.replace(/^(\d{2})(\d{5})(\d{0,4}).*/, '($1) $2-$3');
            } else if (d.length > 6) {
                d = d.replace(/^(\d{2})(\d{4})(\d{0,4}).*/, '($1) $2-$3');
            } else if (d.length > 2) {
                d = d.replace(/^(\d{2})(\d{0,5}).*/, '($1) $2');
            } else if (d.length > 0) {
                d = '(' + d;
            }
            telefone.value = d;
        });
    }

    // ---------- Contador "N de M respondidas" ----------
    var perguntas = form.querySelectorAll('.pergunta');
    var progresso = document.getElementById('progresso');

    function respondida(pergunta) {
        var radios = pergunta.querySelectorAll('input[type="radio"]');
        if (radios.length) {
            return Array.prototype.some.call(radios, function (r) {
                return r.checked;
            });
        }
        var texto = pergunta.querySelector('textarea');
        return !!texto && texto.value.trim() !== '';
    }

    function atualizar() {
        if (!progresso) return;
        var total = 0;
        perguntas.forEach(function (p) {
            if (respondida(p)) total++;
        });
        progresso.textContent = total + ' de ' + perguntas.length + ' respondidas';
    }

    form.addEventListener('input', atualizar);
    form.addEventListener('change', atualizar);
    atualizar();
})();