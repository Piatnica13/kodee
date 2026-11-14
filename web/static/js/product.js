const productId = Number(document.querySelector('#d').value);
const csrfToken = document.querySelector("meta[name='csrf_token']").content;
const images = Array.from(document.querySelectorAll('.productFotos'));
let imageIndex = 0;
function resizeGallery() {
  images.forEach((image, index) => { image.style.opacity = window.innerWidth > 1000 || index === imageIndex ? '1' : '0'; });
}
function moveImage(delta) {
  if (images.length) imageIndex = (imageIndex + delta + images.length) % images.length;
  resizeGallery();
}
document.querySelector('#profilGalochka1').addEventListener('click', () => moveImage(-1));
document.querySelector('#profilGalochka2').addEventListener('click', () => moveImage(1));
window.addEventListener('resize', resizeGallery);
resizeGallery();

async function productAction(url, payload) {
  try {
    const response = await fetch(url, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken}, body:JSON.stringify(payload)});
    const result = await response.json();
    showToast(result.message || result.error || 'Не удалось выполнить действие');
    return response.ok && result.success;
  } catch (_) {
    showToast('Не удалось выполнить действие. Повторите попытку.');
    return false;
  }
}

document.querySelector('#productBth').addEventListener('click', () => productAction('/add_basket', {
  product_id:productId,
  color:document.querySelector('#productColor').value.toLowerCase(),
  size:document.querySelector('#productSize').value,
  material:document.querySelector('#productMaterial').value.toLowerCase()
}));
let favorites = [];
try { favorites = JSON.parse(document.querySelector('#f').value); } catch (_) {}
let isFavorite = Array.isArray(favorites) && favorites.includes(productId);
const outlineHeart = document.querySelector('#productGetLike');
const filledHeart = document.querySelector('#productLike');
function renderFavorite() {
  outlineHeart.style.display = isFavorite ? 'none' : 'flex';
  filledHeart.style.display = isFavorite ? 'flex' : 'none';
  outlineHeart.style.opacity = isFavorite ? '0' : '1';
  filledHeart.style.opacity = isFavorite ? '1' : '0';
}
async function toggleFavorite() {
  if (await productAction('/add_favorite', {product_id:productId})) {
    isFavorite = !isFavorite;
    renderFavorite();
  }
}
outlineHeart.addEventListener('click', toggleFavorite);
filledHeart.addEventListener('click', toggleFavorite);
renderFavorite();
document.querySelector('#productMaterial').addEventListener('change', function() {
  if (['Золото 585 (Белое)', 'Золото 585 (Жёлтое)'].includes(this.value))
    showToast('Изделия из белого и жёлтого золота 585 изготавливаются на заказ, до 2 недель', 10, 5000);
});
