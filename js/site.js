$( document ).ready(function() {
    console.log(window.location.href, window.location.href.indexOf("#access_token="));
    if (window.location.href.indexOf("#access_token=")) {
        var token=$('#access_token');
        var parts = window.location.href.split("#access_token=");
        token.text(parts[1]);
        token.show();
        $('#get_token').hide();
    }
});