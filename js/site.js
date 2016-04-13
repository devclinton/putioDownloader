$( document ).ready(function() {
    if (window.location.href.indexOf("#access_token=") > -1) {
        var token=$('#access_token');
        var parts = window.location.href.split("#access_token=");
        token.text(parts[1]);
        token.show();
        $('#get_token').hide();
    }
});