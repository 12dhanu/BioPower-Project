
document.addEventListener("DOMContentLoaded", function () {

    // Automatically hide notification messages
    const messages = document.querySelectorAll(".message");

    messages.forEach(function (message) {
        setTimeout(function () {
            message.style.opacity = "0";
            message.style.transition = "opacity 0.5s";
        }, 4000);
    });

});
