$(function() {
    // delegate button to listen on click event
    // we're using delegation as the button is dynamically removed/created after calling AJAX
    $("#oxauth-servers-container").on("click", "#remove-oxauth",function() {
        $("#oxauth-servers input:checked").each(function(){
            var srv_id = $(this).attr("data");
            $.post(
                "/api/oxauth_server/" + srv_id,
                {},
                function(data) {
                    $("#oxauth-server-" + srv_id).remove();

                    if ($("#oxauth-servers tr[id*=oxauth-server]").length == 0) {
                        $("#oxauth-servers-container").html("");
                    }
                }
            );
        });
    });

    // add new oxAuth server
    $("#add-oxauth").click(function() {
        var hostname = $("input#add-oxauth-hostname").val();
        var gluu_server = $("input#gluu_server").is(":checked");
        var gluu_version = $("select#gluu_version").val();

        if (hostname != "" | hostname === undefined) {
            $.post(
                "/api/oxauth_server",
                {"hostname": hostname, "gluu_server": gluu_server, "gluu_version": gluu_version},
                function(data) {
                    var html = "";

                    if ($("#oxauth-servers").length == 0) {
                        html += "<p>Available oxAuth servers</p>";
                        html += "<div class='input-group'>";
                        html += "  <table class='table table-bordered' id='oxauth-servers'>";
                        html += "    <thead>";
                        html += "      <tr>";
                        html += "        <th>Hostname</th>";
                        html += "        <th>Gluu Server?</th>";
                        html += "        <th>Version</th>";
                        html += "        <th>Remove?</th>";
                        html += "      </tr>";
                        html += "    </thead>";
                        html += "    <tbody>";
                        html += "    </tbody>";
                        html += "  </table>";
                        html += "  <a href='javascript:void(0)' class='btn btn-danger' id='remove-oxauth'>Remove selected</a>";
                        html += "</div>"
                        $("#oxauth-servers-container").append(html);
                        html = "";
                    }

                    html += "<tr id='oxauth-server-" + data.id + "'>";
                    html += "  <td>" + data.hostname + "</td>";
                    html += "  <td>" + data.gluu_server + "</td>";
                    html += "  <td>" + data.get_version + "</td>";
                    html += "  <td>";
                    html += "    <label class='custom-control custom-checkbox'>";
                    html += "      <input type='checkbox' class='custom-control-input' data='" + data.id + "'>";
                    html += "    </label>";
                    html += "  </td>";
                    html += "</tr>";
                    $("#oxauth-servers tbody").append(html);
                    html = "";
                    $("input#add-oxauth-hostname").val("");
                }
            );
        }
    });

    $("#type-oxeleven").change(function() {
        $("#oxeleven-panel").toggleClass("hidden");
        $("#oxauth-panel").addClass("hidden");
    });

    $("#type-jks").change(function() {
        $("#oxeleven-panel").addClass("hidden");
        $("#oxauth-panel").toggleClass("hidden");
    });
});
