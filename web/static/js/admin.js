const productForm = document.querySelector("#product_form");

productForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    
    const formElement = document.querySelector("#product_form");
    const formData = new FormData(formElement)
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    formData.append("csrf_token", csrfToken);
    
    try{
        const response = await fetch('/admin/add_imgs', {
            method: "POST",
            body: formData
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || 'Ошибка загрузки');
        showToast('Изображения успешно добавлены');
    }
    catch(error){ showToast(error.message || 'Ошибка загрузки'); }

});
