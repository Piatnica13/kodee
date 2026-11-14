function readSelectedItems() {
    try {
        const value = JSON.parse(localStorage.getItem('selectedItems'));
        return Array.isArray(value) ? value.map(String) : null;
    } catch (_) { return null; }
}
document.addEventListener("DOMContentLoaded", () => {
    loadProducts()
    let checkboxs = document.querySelectorAll(".basketcheckboxItem");
    let selected = readSelectedItems();
    
    if(!selected){
        selected = Array.from(checkboxs).map(box => box.dataset.id);
        localStorage.setItem("selectedItems", JSON.stringify(selected));
    }
    
    checkboxs.forEach(box => {
        const id = box.dataset.id;
        box.checked = selected.includes(id);
        
        box.addEventListener("click", () => {
            let update = readSelectedItems() || [];
            
            if (box.checked){
                update.push(id);
                rightProduct();
            }
            else{
                update = update.filter(item => item !== id);
                rightProduct();
            }
            localStorage.setItem("selectedItems", JSON.stringify(update));
        })
    })
})

let allProducts = [];

async function loadProducts() {
    const response = await fetch("/api/products")
    allProducts = await response.json()

    rightProduct()
}


let like = document.querySelectorAll(".basketLike")
let nolike = document.querySelectorAll(".basketNoLike")


function LikeorNo(){
    let favorites = document.querySelector("#basketFavoriteProduct");
    if(favorites){
        favorites = favorites.value.slice(1).slice(0, -1).split(', ')
    }
    
    for(let i = 0; i < like.length; i++){
        id = like[i].dataset.id;
        
        if(favorites.includes(id)){
            Red(id)
        }
        else{
            noRed(id);
        }
    }
}
function Red(element){
    let Id = document.querySelector(`#basketLike${element}`)
    let noId = document.querySelector(`#basketNoLike${element}`)
    noId.style.opacity = "0";
    Id.style.opacity = "1";
    Id.style.display = `flex`;
    noId.style.display = `none`;
}
function noRed(element){
    
    let Id = document.querySelector(`#basketLike${element}`)    
    let noId = document.querySelector(`#basketNoLike${element}`)
    Id.style.opacity = "0";
    noId.style.opacity = "1";
    Id.style.display = `none`;
    noId.style.display = `flex`;
}
LikeorNo()
function Like(event){
    let element = event.currentTarget;
    let Id = element.dataset.id; 
    let productLike = document.querySelector(`#basketLike${Id}`)
    let productNoLike = document.querySelector(`#basketNoLike${Id}`)
    

    if (productLike.style.display == 'flex') {
        productLike.style.opacity = '0';
        productNoLike.style.display = 'flex';
        productNoLike.style.opacity = '1';
        productLike.style.display = 'none';
    }
    else{
        productNoLike.style.opacity = '0';
        productLike.style.display = 'flex';
        productLike.style.opacity = '1';
        productNoLike.style.display = 'none';
    } 

    let token = document.querySelector('meta[name="csrf_token"]').getAttribute('content');
    
    fetch('/add_favorite', {
        method: "POST",
        credentials: "include",
        headers: { 
            'Content-Type': 'application/json',
            "X-CSRFToken": token
        },
        body: JSON.stringify({product_id: parseInt(Id)})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success){
            showToast(data.message)
        }
        else{
            showToast(data.error)
        }
    })
}

like.forEach(element => {
    element.addEventListener("click", Like)
});
nolike.forEach(element => {
    element.addEventListener("click", Like)
});

let delete_product= document.querySelectorAll(".basketDelete");
let checkboxs = document.querySelectorAll(".basketcheckboxItem");
function deleteFunc(event){
    let element = event.currentTarget;
    let Id = element.dataset.id; 

    checkboxs.forEach((el) => {
        if (el.dataset.id == Id){
            el.checked = false;
        }
    });

    rightProduct();
    
    let token = document.querySelector("meta[name='csrf_token']").getAttribute("content");

    fetch("/delete_basket", {
        method: "POST",
        credentials: "include",
        headers: { 
            'Content-Type': 'application/json',
            "X-CSRFToken": token },
        body: JSON.stringify({product_id: parseInt(Id)})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success){
            removeDiv = document.querySelector(`#card-${Id}`)
            removeDiv.remove();

            let update = readSelectedItems() || [];
            update = update.filter(item => item !== Id);
            localStorage.setItem("selectedItems", JSON.stringify(update));
            showToast(data.message)
        }
        else{
            showToast(data.error)
        }
    })
}
delete_product.forEach(element => {
    element.addEventListener("click", deleteFunc)
});

let divForProduct = document.querySelector("#basketProductsPay");
function rightProduct() {
    let basketPay = document.querySelector("#basketPay");
    let num = 1;
    let sum = 0;
    checkboxs.forEach(box => {
        const productId = box.dataset.id
        const product = allProducts.find(item => item.id == productId);
        
        try {
            let productDiv = document.querySelector(`#basketRightProductId${box.dataset.id}`)
            productDiv.remove();
        } catch (error) {}
        if (box.checked == true && product){
            let productShow = document.createElement("div");
            productShow.innerHTML += `<p style = "font-size: 1.2rem">${num}. ${escapeHTML(product.name)} — ${escapeHTML(product.price)}&#8376;</p>`;
            productShow.classList.add("basketRightProducts");
            productShow.id = `basketRightProductId${productId}`;

            divForProduct.appendChild(productShow)
            num++;
            sum += Number(product.price) || 0;
        }
    });
    basketPay.innerHTML = `<h3 style = "font-size: 1.5rem">К оплате — ${sum}&#8376;</h3>`;
}

let messageBth = document.querySelector("#basketWhatsAppBth");
messageBth.addEventListener("click", messageBthFunc)

function messageBthFunc() {
    const selected = Array.from(checkboxs).filter(box => box.checked)
        .map(box => ({id: box.dataset.id, product: allProducts.find(item => item.id == box.dataset.id)}))
        .filter(item => item.product && document.getElementById(`card-${item.id}`));
    if (!selected.length) { showToast('Выберите товары для заказа'); return; }
    const addressValue = document.querySelector('#basketAddress').value;
    if (!addressValue) {
        formAddress.style.display = 'block';
        setTimeout(() => { formAddress.style.opacity = '1'; showToast('Адрес не указан'); }, 1);
        return;
    }
    const customer = document.querySelector('#basketNamehidden').value;
    const lines = [`Здравствуйте! Меня зовут ${customer}. Хочу оформить заказ.`];
    selected.forEach(({id, product}, index) => {
        const card = document.getElementById(`card-${id}`);
        lines.push(`${index + 1}) ${product.name}`,
            card.querySelector('.basketColor').innerText,
            card.querySelector('.basketSize').innerText,
            card.querySelector('.basketmaterial').innerText);
    });
    lines.push(`Удобна доставка на адрес ${addressValue}`);
    window.open(`https://wa.me/77003360024?text=${encodeURIComponent(lines.join('\n'))}`, '_blank', 'noopener,noreferrer');
}

let bthAdd = document.querySelector("#ProfilAddBth");
bthAdd.addEventListener('click', ()=>{
    formAddress.style.opacity = `0`;
    setTimeout(() => {
        formAddress.style.display = `none`;
    }, 300);


    let name = document.querySelector("#basketName");
    let city = document.querySelector("#basketCity");
    let street = document.querySelector("#basketStreet");
    let home = document.querySelector("#basketHome");
    let flat = document.querySelector("#basketFlat");

    let token = document.querySelector("meta[name='csrf_token']").getAttribute("content");


    fetch('/add_address', {
        method: "POST",
        credentials: "include",
        headers: { 
            "Content-Type": "application/json",
            "X-CSRFToken": token
         },
        body: JSON.stringify({name: name.value, city: city.value, street: street.value, home: home.value, flat: flat.value})
      })
        .then(response =>response.json())
        .then(data => {
          if(data.success){
            document.querySelector("#basketAddress").value = data.address;
            showToast(data.message);
          }
          else{
            showToast(data.error)
          }
    })
})

let formAddress = document.querySelector("#ProfilAddSplit");
formAddress.style.opacity = `0`;
formAddress.style.display = `none`;
formAddress.style.transition = `opacity 0.3s ease-in-out`