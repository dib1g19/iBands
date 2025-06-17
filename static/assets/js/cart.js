document.addEventListener('DOMContentLoaded', function() {
    const showBtn = document.getElementById('show-new-address-form');
    const formDiv = document.getElementById('new-address-form');

    if (showBtn && formDiv) {
        showBtn.addEventListener('click', function() {
            formDiv.style.display = 'block';
            showBtn.style.display = 'none';
        });
    }

    document.querySelectorAll('#save-address-btn').forEach(function(saveBtn) {
        saveBtn.addEventListener('click', function() {
            const parent = saveBtn.closest('#new-address-form');
            const data = new FormData();
            parent.querySelectorAll('input, select').forEach(function(input) {
                data.append(input.name, input.value);
            });

            fetch("{% url 'customer:quick_add_address' %}", {
                method: 'POST',
                body: data,
                headers: {
                    'X-CSRFToken': '{{ csrf_token }}'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // For logged-in users: Add new address to the address list and auto-select it
                    if (document.getElementById('address-list-row')) {
                        const newCard = document.createElement('div');
                        newCard.className = "col-xl-4 col-lg-4 col-md-6 col-sm-12";
                        newCard.innerHTML = `
                            <div class="card-wrap border rounded mb-4">
                                <div class="card-wrap-header px-3 py-2 br-bottom d-flex align-items-center justify-content-between">
                                    <div class="card-heafder-flex">
                                        <h4 class="fs-md ft-bold mb-1">Адрес за доставка <i class="fas fa-check text-success"></i></h4>
                                    </div>
                                </div>
                                <div class="card-wrap-body px-3 py-3">
                                    <p class="mb-0"><span class="fw-bold">Пълно Име: </span>${parent.querySelector('[name="full_name"]').value}</p>
                                    <p class="mb-0"><span class="fw-bold">Имейл: </span>${parent.querySelector('[name="email"]').value}</p>
                                    <p class="mb-0"><span class="fw-bold">Телефон: </span>${parent.querySelector('[name="mobile"]').value}</p>
                                    <p class="mb-0"><span class="fw-bold">Метод на доставка: </span>${parent.querySelector('[name="delivery_method"]').selectedOptions[0].text}</p>
                                    <p class="mb-0"><span class="fw-bold">Град: </span>${parent.querySelector('[name="city"]').value}</p>
                                    <p class="mb-3"><span class="fw-bold">Адрес: </span>${parent.querySelector('[name="address"]').value}</p>
                                    <div class="mt-3">
                                        <input id="address${data.address_id}" value="${data.address_id}" class="radio-custom" name="address" type="radio" checked>
                                        <label for="address${data.address_id}" class="radio-custom-label">Избери адрес</label>
                                    </div>
                                </div>
                            </div>
                        `;
                        document.getElementById('address-list-row').appendChild(newCard);

                        parent.style.display = 'none';
                        if (showBtn) showBtn.style.display = 'block';
                    } else {
                        alert('Адресът е запазен. Можете да продължите с поръчката!');
                    }
                } else {
                    alert("Грешка при добавяне на адрес!");
                }
            });
        });
    });
});
document.querySelector('form').addEventListener('submit', function(e) {
    var newAddressForm = document.getElementById('new-address-form');
    if (newAddressForm && newAddressForm.style.display === 'none') {
        // Disable all inputs in the new address form so they aren't submitted
        newAddressForm.querySelectorAll('input, select, button').forEach(function(input) {
            input.disabled = true;
        });
    } else if (newAddressForm && newAddressForm.style.display !== 'none') {
        // Ensure inputs are enabled if adding new address (just in case)
        newAddressForm.querySelectorAll('input, select, button').forEach(function(input) {
            input.disabled = false;
        });
    }
});
