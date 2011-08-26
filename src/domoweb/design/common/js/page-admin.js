function getPluginsList() {
	$("#plugins_list li").remove();
    
    rinor.get(['plugin', 'list'])
        .success(function(data, status, xhr){
            $.each(data, function() {
                if (this.list.length > 0) { // If a least 1 plugin is enabled
                    var host = this.host;
                    $.each(this.list, function() {
                        var technology = this.technology.replace(' ', '');
                        if ($("#plugins_list ul#menu_" + technology).length == 0) {
                            $("#plugins_list").append("<li><div class='titlenav2 icon16-technology-" + technology + "'>" + technology + "</div><ul id='menu_" + technology + "'></ul></li>")
                        }
                        var li = $("<li class='" + this.type + "'></li>");
                        var a = $("<a></a>");
                        a.attr('href', '/admin/plugin/' + host + "/" + this.name + "/" + this.type)
                            .attr('title', this.description)
                            .tooltip_right();
                        var status = $("<div><div class='host'>" + host + "</div>" + this.name + "</div>");
                        if (this.name != 'rest') {
                            status.addClass("menu-indicator")
                            if (this.status == 'ON') {
                                if (this.type == 'plugin') {
                                    status.addClass("icon16-status-software-up");
                                    status.append("<span class='offscreen'>Software Running</span>");                                    
                                } else { // hardware
                                    status.addClass("icon16-status-hardware-up");
                                    status.append("<span class='offscreen'>Hardware Running</span>");                                                                        
                                }
                            } else {
                                if (this.type == 'plugin') {
                                    status.addClass("icon16-status-software-down");
                                    status.append("<span class='offscreen'>Software Stopped</span>");
                                } else { // hardware
                                    status.addClass("icon16-status-hardware-down");
                                    status.append("<span class='offscreen'>Hardware Stopped</span>");
                                }
                            }
                        }
                        a.append(status);
                        li.append(a);
                        $("#plugins_list ul#menu_" + technology).append(li);	
                    });
                } else {
                    var li = $("<li></li>");
                    var a = $("<a>No plugin enabled yet<br />Click to reload</a>");
                    a.attr('href', '#');
                    a.addClass("icon16-status-error");
                    a.click(function(){getPluginsList();})
                    li.append(a);
                    $("#plugins_list").append(li);
                }                    
            });
        })
        .error(function(jqXHR, status, error){
            var li = $("<li></li>");
            var a = $("<a>" + jqXHR.responseText + " <br />Click to reload</a>");
            a.attr('href', '#');
            a.addClass("icon16-status-error");
            a.click(function(){getPluginsList();})
            li.append(a);
            $("#plugins_list").append(li);	
        });
}
