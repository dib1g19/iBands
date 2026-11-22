// One checkout form for every courier we host. A courier supplies its lookups, quote, and the fields its API needs.
(function () {
    function el(id) {
        return document.getElementById(id);
    }
    function text(node) {
        return (node && node.value ? node.value : '').trim();
    }
    function postalOf(item) {
        return (item && (item.postCode || item.postcode || item.postal_code)) || '';
    }
    function labelOf(item) {
        return ((item.type || '') + ' ' + (item.name || '')).trim();
    }
    function norm(value) {
        return (value || '').toString().trim().toLowerCase();
    }
    function findMatch(items, id, name) {
        var list = items || [];
        var byId = id && list.find(function (item) { return String(item.id) === String(id); });
        if (byId) return byId;
        var wanted = norm(name);
        if (!wanted) return null;
        return list.find(function (item) {
            return norm(labelOf(item)) === wanted || norm(item.name) === wanted;
        }) || null;
    }
    function clearBox(node) {
        if (!node) return;
        node.innerHTML = '';
        node.style.display = 'none';
    }
    function option(label, onPick) {
        var link = document.createElement('a');
        link.href = '#';
        link.className = 'list-group-item list-group-item-action';
        link.textContent = label;
        link.addEventListener('click', function (event) {
            event.preventDefault();
            onPick();
        });
        return link;
    }

    window.deliveryForms = {};

    window.bindDeliveryForm = function (config) {
        var carrier = config.carrier;
        var citySearch = el(carrier + '_city_search');
        var citySuggestions = el(carrier + '_city_suggestions');
        var cityIdInput = el(carrier + '_' + config.cityKey);
        var officeSearch = el(carrier + '_office_search');
        var officeSuggestions = el(carrier + '_office_suggestions');
        var officeCodeInput = el(carrier + '_office_code');
        var officeNameHidden = el(carrier + '_office_name');
        var officeTypeInput = config.lockerMethod ? el(carrier + '_office_type') : null;
        var addressInput = config.street ? null : el(carrier + '_address');
        var streetSearch = config.street ? el(carrier + '_street_search') : null;
        var streetSuggestions = config.street ? el(carrier + '_street_suggestions') : null;
        var streetIdInput = config.street ? el(carrier + '_street_id') : null;
        var streetNumber = config.street ? el(carrier + '_street_number') : null;
        var postCodeInput = el(carrier + '_post_code');
        var modeOffice = el(carrier + '_mode_office');
        var modeAddress = el(carrier + '_mode_address');
        var quoteTimer = null;
        var saveTimer = null;
        var cityTimer = null;
        var streetTimer = null;
        var lastKey = null;

        function selected() {
            var radio = el('shipping-' + carrier);
            return !!(radio && radio.checked);
        }
        function officeMode() {
            var mode = document.querySelector('input[name="' + carrier + '_delivery_mode"]:checked');
            return !!(mode && mode.value === 'office');
        }
        function method() {
            if (!officeMode()) return config.door;
            if (config.lockerMethod && officeTypeInput && officeTypeInput.value === 'locker') return config.lockerMethod;
            return config.office;
        }
        function addressLine() {
            if (!config.street) return text(addressInput);
            return (text(streetSearch) + ' ' + text(streetNumber)).trim();
        }
        function payload(withPrice) {
            var office = officeMode();
            var body = {
                name: text(el(carrier + '_name')),
                phone: text(el(carrier + '_phone')),
                email: text(el(carrier + '_email')),
                face: text(el(carrier + '_face')),
                delivery_method: method(),
                city: text(citySearch),
                address: office ? '' : addressLine(),
                office_code: office ? text(officeCodeInput) : '',
                office_name: office ? text(officeNameHidden) : '',
                post_code: text(postCodeInput)
            };
            body[config.cityKey] = text(cityIdInput);
            if (config.street) {
                body.street_id = office ? '' : text(streetIdInput);
                body.street_number = office ? '' : text(streetNumber);
            }
            if (withPrice) body.shipping_price = config.price.shipping_price_cod || null;
            return body;
        }
        function quote() {
            clearTimeout(quoteTimer);
            quoteTimer = setTimeout(function () {
                var body = payload(false);
                var url = config.quoteUrl(body);
                if (!url) return;
                fetch(url)
                    .then(function (response) { return response.json(); })
                    .then(function (data) {
                        if (data && data.quote && data.quote.price != null) {
                            config.price.shipping_price_cod = parseFloat(data.quote.price).toFixed(2);
                            updateSummaryForPayment();
                        }
                    })
                    .catch(function () {});
            }, 300);
        }
        function save() {
            if (!window.ownsCheckout || !selected()) return;
            clearTimeout(saveTimer);
            saveTimer = setTimeout(function () {
                var body = payload(false);
                var key = JSON.stringify(body);
                if (key === lastKey) return;
                fetch(config.saveUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                }).then(function (response) { return response.json(); }).then(function (data) {
                    if (data && data.success) lastKey = key;
                }).catch(function () {});
            }, 400);
        }
        function changed() {
            quote();
            save();
        }
        function clearOffice() {
            if (officeSearch) officeSearch.value = '';
            if (officeCodeInput) officeCodeInput.value = '';
            if (officeNameHidden) officeNameHidden.value = '';
            if (officeTypeInput) officeTypeInput.value = '';
            clearBox(officeSuggestions);
        }
        function clearStreet() {
            if (streetSearch) streetSearch.value = '';
            if (streetIdInput) streetIdInput.value = '';
            if (streetNumber) streetNumber.value = '';
            clearBox(streetSuggestions);
        }
        function renderChoices(container, items, label, onPick) {
            clearBox(container);
            (items || []).slice(0, 10).forEach(function (item) {
                container.appendChild(option(label(item), function () { onPick(item); }));
            });
            if (container.childElementCount) container.style.display = 'block';
        }
        function cityLabel(item) {
            return config.cityText ? config.cityText(item) : labelOf(item);
        }
        function pickCity(item) {
            citySearch.value = config.cityValue ? config.cityValue(item) : labelOf(item);
            cityIdInput.value = item.id || '';
            if (postCodeInput && postalOf(item)) postCodeInput.value = postalOf(item);
            clearOffice();
            clearStreet();
            clearBox(citySuggestions);
            config.offices(cityIdInput.value).then(function (offices) {
                officeSuggestions._all = offices || [];
                renderChoices(officeSuggestions, officeSuggestions._all, officeText, pickOffice);
            }).catch(function () {});
            changed();
        }
        function pickOffice(item) {
            officeSearch.value = item.name || '';
            officeCodeInput.value = item.id || '';
            officeNameHidden.value = item.name || '';
            if (officeTypeInput) officeTypeInput.value = item.type || 'office';
            if (postCodeInput && postalOf(item)) postCodeInput.value = postalOf(item);
            clearBox(officeSuggestions);
            changed();
        }
        function officeText(item) {
            if (config.officeText) return config.officeText(item);
            return item.name || ('Офис ' + item.id);
        }
        function pickStreet(item) {
            streetSearch.value = labelOf(item);
            streetIdInput.value = item.id || '';
            if (postCodeInput && postalOf(item)) postCodeInput.value = postalOf(item);
            clearBox(streetSuggestions);
            changed();
        }
        function setMode(mode, persist) {
            var office = mode === 'office';
            if (modeOffice) modeOffice.checked = office;
            if (modeAddress) modeAddress.checked = !office;
            document.querySelectorAll('.' + carrier + '-address-field').forEach(function (node) {
                node.style.display = office ? 'none' : 'block';
            });
            document.querySelectorAll('.' + carrier + '-office-field').forEach(function (node) {
                node.style.display = office ? 'block' : 'none';
            });
            if (office) {
                clearStreet();
                if (addressInput) addressInput.value = '';
            } else {
                clearOffice();
            }
            if (persist) changed();
        }
        function setPostalFrom(item) {
            if (postCodeInput && item && postalOf(item)) postCodeInput.value = postalOf(item);
        }
        async function apply(dest) {
            var office = dest.delivery_method !== config.door;
            setMode(office ? 'office' : 'address', false);
            window.fillContactFields(carrier + '_', dest, true);
            if (postCodeInput && dest.post_code) postCodeInput.value = dest.post_code;
            if (citySearch) citySearch.value = dest.city || '';
            var cityId = dest[config.cityKey] || '';
            if (cityIdInput) cityIdInput.value = cityId;
            var streetLabel = '';
            if (office) {
                if (officeSearch) officeSearch.value = dest.office_name || '';
                if (officeCodeInput) officeCodeInput.value = dest.office_code || '';
                if (officeNameHidden) officeNameHidden.value = dest.office_name || '';
                if (officeTypeInput) officeTypeInput.value = dest.delivery_method === config.lockerMethod ? 'locker' : 'office';
            } else if (config.street) {
                var number = dest.street_number || '';
                if (streetNumber) streetNumber.value = number;
                streetLabel = (dest.address || '').trim();
                if (number && streetLabel.toLowerCase().endsWith(number.toLowerCase())) {
                    streetLabel = streetLabel.slice(0, -number.length).trim();
                }
                if (streetSearch) streetSearch.value = streetLabel;
                if (streetIdInput) streetIdInput.value = dest.street_id || '';
            } else if (addressInput) {
                addressInput.value = dest.address || '';
            }
            if (!cityId && (dest.city || '').trim().length >= 2) {
                try {
                    var city = findMatch(await config.cities(dest.city), '', dest.city);
                    if (city) {
                        cityId = city.id || '';
                        if (cityIdInput) cityIdInput.value = cityId;
                        if (citySearch) citySearch.value = labelOf(city);
                        if (!dest.post_code) setPostalFrom(city);
                    }
                } catch (e) { /* keep the stored city text */ }
            }
            if (office && cityId) {
                try {
                    var offices = await config.offices(cityId);
                    officeSuggestions._all = offices || [];
                    var picked = findMatch(offices, dest.office_code, dest.office_name);
                    if (picked) {
                        officeSearch.value = picked.name || '';
                        officeCodeInput.value = picked.id || '';
                        officeNameHidden.value = picked.name || '';
                        if (officeTypeInput) officeTypeInput.value = picked.type || officeTypeInput.value;
                        setPostalFrom(picked);
                    }
                } catch (e) { /* keep the stored office text */ }
            } else if (!office && config.street && !dest.street_id && cityId && streetLabel.length >= 2) {
                try {
                    var street = findMatch(await config.streets(cityId, streetLabel), '', streetLabel);
                    if (street) {
                        if (streetSearch) streetSearch.value = labelOf(street);
                        if (streetIdInput) streetIdInput.value = street.id || '';
                        setPostalFrom(street);
                    }
                } catch (e) { /* keep the stored street text */ }
            }
            changed();
        }
        function pay(button, paymentType) {
            var body = payload(true);
            var errorBlock = el(carrier + '-error-block');
            if (errorBlock) errorBlock.innerHTML = '';
            if (!config.ready(body)) {
                if (errorBlock) {
                    errorBlock.innerHTML = '<div class="alert alert-danger">Моля, попълнете адреса за доставка за ' + config.label + '!</div>';
                    errorBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                setContinueLoading(false);
                return;
            }
            button.innerHTML = (paymentType === 'card' ? 'Плащане с карта' : 'Наложен платеж') + ' <i class="fas fa-spinner fa-spin ms-2"></i>';
            fetch(config.saveUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            }).then(function (response) { return response.json(); }).then(function (data) {
                if (!data.success) {
                    if (errorBlock) {
                        errorBlock.innerHTML = '<div class="alert alert-danger">Възникна неочаквана грешка при запазване на адреса (' + config.label + '). Моля, опитайте отново.</div>';
                        errorBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    button.innerHTML = paymentType === 'card' ? 'Плащане с карта' : 'Наложен платеж';
                    setContinueLoading(false);
                    return;
                }
                if (paymentType === 'card') {
                    fetch(config.cardUrl, {
                        method: 'POST',
                        body: JSON.stringify({ email: body.email })
                    }).then(function (response) { return response.json(); })
                        .then(function (session) { return stripe.redirectToCheckout({ sessionId: session.sessionId }); })
                        .then(function (result) {
                            if (result.error) {
                                if (window.Toast) window.Toast.fire({ icon: 'error', title: result.error.message });
                                else alert(result.error.message);
                            }
                        }).catch(function (error) { console.log('Error: ', error); });
                    return;
                }
                fetch(config.codUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrftoken }
                }).then(function (response) {
                    if (response.redirected) window.location.href = response.url;
                });
            }).catch(function () {
                if (errorBlock) {
                    errorBlock.innerHTML = '<div class="alert alert-danger">Възникна неочаквана грешка при запазване на адреса (' + config.label + '). Моля, опитайте отново.</div>';
                    errorBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                button.innerHTML = paymentType === 'card' ? 'Плащане с карта' : 'Наложен платеж';
                setContinueLoading(false);
            });
        }

        if (citySearch) {
            citySearch.addEventListener('input', function () {
                clearTimeout(cityTimer);
                cityIdInput.value = '';
                clearOffice();
                if (streetIdInput) streetIdInput.value = '';
                var query = citySearch.value.trim();
                cityTimer = setTimeout(function () {
                    config.cities(query).then(function (cities) {
                        renderChoices(citySuggestions, cities, cityLabel, pickCity);
                    }).catch(function () {});
                }, 300);
                save();
            });
        }
        if (officeSearch) {
            officeSearch.addEventListener('input', function () {
                officeCodeInput.value = '';
                officeNameHidden.value = '';
                if (officeTypeInput) officeTypeInput.value = '';
                var all = officeSuggestions._all || [];
                var query = officeSearch.value.toLowerCase();
                var filtered = query ? all.filter(function (item) {
                    return (item.name || '').toLowerCase().indexOf(query) !== -1;
                }) : all;
                renderChoices(officeSuggestions, filtered, officeText, pickOffice);
                save();
            });
        }
        if (streetSearch) {
            streetSearch.addEventListener('input', function () {
                clearTimeout(streetTimer);
                streetIdInput.value = '';
                var query = streetSearch.value.trim();
                streetTimer = setTimeout(function () {
                    if (!cityIdInput.value || query.length < 2) {
                        clearBox(streetSuggestions);
                        return;
                    }
                    config.streets(cityIdInput.value, query).then(function (streets) {
                        renderChoices(streetSuggestions, streets, labelOf, pickStreet);
                    }).catch(function () {});
                }, 300);
                changed();
            });
        }
        [addressInput, streetNumber].forEach(function (input) {
            if (input) input.addEventListener('input', changed);
        });
        ['name', 'face', 'phone', 'email'].forEach(function (field) {
            var input = el(carrier + '_' + field);
            if (input) input.addEventListener('input', save);
        });
        document.addEventListener('click', function (event) {
            if (citySuggestions && !citySuggestions.contains(event.target) && event.target !== citySearch) clearBox(citySuggestions);
            if (streetSuggestions && !streetSuggestions.contains(event.target) && event.target !== streetSearch) clearBox(streetSuggestions);
            if (officeSuggestions && !officeSuggestions.contains(event.target) && event.target !== officeSearch) clearBox(officeSuggestions);
        });
        if (modeOffice && modeAddress) {
            setMode('office', false);
            modeAddress.addEventListener('change', function () { if (this.checked) setMode('address', true); });
            modeOffice.addEventListener('change', function () { if (this.checked) setMode('office', true); });
        }
        var radio = el('shipping-' + carrier);
        if (radio) {
            radio.addEventListener('change', function () {
                if (!radio.checked) return;
                config.price.shipping_price_cod = null;
                updateSummaryForPayment();
                changed();
            });
        }
        var rows = window.savedForCarrier(carrier);
        var saved = el(carrier + '-saved');
        window.renderSavedDestinations(saved, rows, apply);
        var initial = window.initialDestination(carrier);
        if (initial) {
            apply(initial);
            var match = rows.filter(function (dest) { return window.sameDestination(dest, initial); })[0];
            if (match) window.markSavedDestination(saved, match.id);
        } else if (window.ownsCheckout) {
            window.fillContactFields(carrier + '_', null, false);
        }

        window.deliveryForms[carrier] = { payload: payload, quote: quote, pay: pay };
    };

    window.payDelivery = function (carrier, button, paymentType) {
        var form = window.deliveryForms[carrier];
        if (!form) {
            setContinueLoading(false);
            return;
        }
        form.pay(button, paymentType);
    };

    function setShippingBlock(block, open) {
        if (!block) return;
        var panel = block.querySelector('.shipping-panel');
        if (!panel) return;
        if (panel._anim) {
            var held = panel.getBoundingClientRect().height;
            panel._anim.onfinish = null;
            panel._anim.cancel();
            panel.style.height = held + 'px';
            panel._anim = null;
        }
        var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var from = panel.getBoundingClientRect().height;
        if (open) {
            block.classList.add('open');
            block.classList.remove('settled');
            var to = panel.scrollHeight;
            var finish = function () {
                if (!block.classList.contains('open')) return;
                panel.style.height = 'auto';
                block.classList.add('settled');
            };
            if (reduce || Math.abs(to - from) < 1) {
                finish();
                return;
            }
            panel.style.height = from + 'px';
            panel._anim = panel.animate(
                [{ height: from + 'px' }, { height: to + 'px' }],
                { duration: 320, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'forwards' }
            );
            panel._anim.onfinish = function () {
                panel.style.height = 'auto';
                panel._anim.cancel();
                panel._anim = null;
                finish();
            };
            return;
        }
        if (!block.classList.contains('open') && from < 1) return;
        block.classList.remove('settled', 'open');
        if (reduce || from < 1) {
            panel.style.height = '0px';
            return;
        }
        panel.style.height = from + 'px';
        panel._anim = panel.animate(
            [{ height: from + 'px' }, { height: '0px' }],
            { duration: 320, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'forwards' }
        );
        panel._anim.onfinish = function () {
            panel.style.height = '0px';
            panel._anim.cancel();
            panel._anim = null;
        };
    }

    document.addEventListener('DOMContentLoaded', function () {
        var carriers = ['econt', 'speedy', 'pigeon'];
        var blocks = carriers.map(function (carrier) {
            return { radio: el('shipping-' + carrier), block: el(carrier + '-shipping-block') };
        }).filter(function (item) { return item.radio && item.block; });
        function updateShippingBlock() {
            blocks.forEach(function (item) { setShippingBlock(item.block, item.radio.checked); });
        }
        if (!blocks.length) return;
        blocks.forEach(function (item) { item.radio.addEventListener('change', updateShippingBlock); });
        updateShippingBlock();
    });
})();
