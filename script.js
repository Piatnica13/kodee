let checkboxSubmenu1 = document.querySelector("#checkboxx");
let divSrtelkaMenu = document.querySelector("#strelkaMenuOp");
let chet = true;
checkboxSubmenu1.addEventListener('click', () =>{
    divSrtelkaMenu.classList.toggle('open');
    if(chet == true){
        divSrtelkaMenu.style.height = "100px";
        chet = false;
    }
    else{
        interval2 = setInterval(()=>{
            divSrtelkaMenu.style.height = "0px";
            clearInterval(interval2)
        }, 300);
        chet = true;
    }
});
let checkboxMain = document.querySelector("#checkboxMain");
let PodMenu = document.querySelector("#PodMenu");
let MainMenu = document.querySelector('#contenerMenu')
let PodMenuPh = document.querySelector('#PodMenuPh')
PodMenuPh.classList.toggle('open');
  
let chetPodMenu = false;
let body = document.querySelector('#Body');
let PodTextPh = document.querySelector('.PodTextPh')

checkboxMain.addEventListener('click', checkboxmainn) 
function checkboxmainn(){
    if(chetPodMenu == false){
        PodMenu.style.height = `360px`;
        chetPodMenu = true;
        if (window.innerWidth <= 768){
            body.style.opacity =  "0";
            interval5 = setTimeout(()=>{
                PodMenuPh.classList.toggle('open');
            }, 200)
            PodMenuPh.style.height = "auto";
        }
    }
    else{
        chetPodMenu = false;
        PodMenu.style.height = `0px`;
        if (window.innerWidth <= 768){
            PodMenuPh.classList.toggle('open');
            body.style.opacity =  "1";
            let interval4 = setInterval(() =>{
                PodMenuPh.style.height = "0px";
                clearInterval(interval4);
            }, 450)
        }
    }
}

function checkWidth() {
    if (window.innerWidth <= 768) {
        if(divSrtelkaMenu.classList.toggle('open') == true){
            console.log(divSrtelkaMenu.classList.toggle('open'));
        }
        chetPodMenu = true;
        checkboxmainn();
        checkboxMain.checked = false;
    } 
}
checkWidth();

// Проверка при изменении размера окна
window.addEventListener('resize', checkWidth);
