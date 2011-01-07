

// Variables.
// ---------------------------------------------------------------------------------------------------------------------
var chatWidth = 298;
var chatHeight = 534;
var chatX = 0;
var chatY = 0;
var docked = true;
var hidden = false;
var popup = false;
var fontsize = 10;
var timestamp = false;
var scrollLock = false;


// Connect to the background script.
// ---------------------------------------------------------------------------------------------------------------------
var port = chrome.extension.connect();


// Deal with messages from the background script.
// ---------------------------------------------------------------------------------------------------------------------
port.onMessage.addListener(function(msg)
{

    // Debug message.
    //console.log(JSON.stringify(msg));

    if(msg.command == "set position")
    {   
        chatWidth = msg.chatWidth? msg.chatWidth : chatWidth;
        chatHeight = msg.chatHeight? msg.chatHeight : chatHeight;
        chatX = msg.chatX? msg.chatX : chatX;
        chatY = msg.chatY? msg.chatY : chatY;
        redraw();
    }
    
    else if(msg.command == "initialize")
    {
        port.postMessage({command: "initialize", userName: getUserName(), 
                          chatX: $(window).width() - (chatWidth + 8),
                          chatY: $(window).height() - (chatHeight + 8)});
        redraw();
    }

    else if(msg.command == "printf")
    {
        printf(msg.text, msg.color, msg.weight, msg.click);
    }

    else if(msg.command == "set population")
    {
        $("#people").html(msg.population);
    }
    
    else if(msg.command == "set connection")
    {
        if(msg.connected){
            $("#connect")[0].src = chrome.extension.getURL("connect.png");
        } 
        else{
            $("#connect")[0].src = chrome.extension.getURL("exclamation.png");
        }
    }
    
    else if(msg.command == "set hidden")
    {
        hidden = msg.hidden;
        if(hidden){
            $("#minmax")[0].src = chrome.extension.getURL("add.png");
        }
        else{
            $("#chattit").css("background-color", "rgba(206, 227, 248, 0.9)");
            $("#minmax")[0].src = chrome.extension.getURL("sub.png");
        }
        redraw();
    }
    
    else if(msg.command == "set docked")
    {
        docked = msg.docked;
        if(docked)
        {
            $("#dock")[0].src = chrome.extension.getURL("arrow_left.png");
        }
        else
        {
            $("#dock")[0].src = chrome.extension.getURL("arrow_right.png");
        }
        redraw();
    }
    
    else if(msg.command == "set timestamp")
    {
        timestamp = msg.timestamp;
        if(timestamp)
        {
            $(".timestamp").show();
            $("#timestamp")[0].src = chrome.extension.getURL("time_delete.png");
        }
        else
        {
            $(".timestamp").hide();
            $("#timestamp")[0].src = chrome.extension.getURL("time_add.png");
        }
    }
    
    else if(msg.command == "set popup")
    {
        popup = msg.popup;
        if(popup)
        {
            $("#chattitPopup").show();
        }
        else
        {
            $("#chattitPopup").hide();
        }            
        redraw();
    }

    else if(msg.command == "set top ten")
    {
        topten = []
        for(var tt in msg.topten)
        {
            topten.push([tt, msg.topten[tt]]);
        }
        topten = topten.sort(function(a, b){return b[1] - a[1];});
        newtop = "";
        newtop += "<table>";
        for(var tt = 0; tt < topten.length; tt++)
        {
            newtop += "<tr>";
                newtop += "<td style='text-align:right'>";
                    newtop += topten[tt][1];
                newtop += "</td>";
                newtop += "<td>";
                    newtop += "&nbsp;&nbsp;<a target='_blank' href='http://www.reddit.com" + topten[tt][0] + "'>" + topten[tt][0] + "</a>";
                newtop += "</td>";
            newtop += "</tr>";
        }
        newtop += "</table>";
        $("#topreddits").html(newtop);
    }
    
    // Print a warning.
    else if(msg.command == "warning")
    {
        printf(msg.warning + "<br>", "red", "bold");
    }
    
    // Print info from server.
    else if(msg.command == "info")
    {
        printf(msg.info + "<br>", "darkblue", "bold");
    }
    
    // Print info from server.
    else if(msg.command == "set fontsize")
    {
        fontsize = msg.fontsize;
        $("#chat").css("font-size", fontsize)
    }
    
});


// Initialization.
// ---------------------------------------------------------------------------------------------------------------------
$(document).ready(function()
{
    $("body").append("<div class='chattit' id='chattit'></div>");
    chrome.extension.sendRequest({command: "load", url: chrome.extension.getURL("chattit.html")}, function(response){
        $("#chattit").html(response.content);
        $("#chattitPopup").hide();
        $("#userPopup").hide();
        $("#chat").scroll(function()
        {
            if($("#chat").attr("scrollTop") + $("#chat").height() != $("#chat").attr("scrollHeight"))
            {            
                scrollLock = true;
            }
            else
            {
                scrollLock = false;
            }
        });
        $("#logo")[0].src = chrome.extension.getURL("logo.png");        
        $("#popupButton")[0].src = chrome.extension.getURL("information.png");        
        $("#fontup")[0].src = chrome.extension.getURL("font_add.png");        
        $("#fontdown")[0].src = chrome.extension.getURL("font_delete.png");        
        $("#refresh")[0].src = chrome.extension.getURL("refresh.png");        
        $("#minmax").click(function(){port.postMessage({command: "toggle hidden"});});
        $("#dock").click(function(){port.postMessage({command: "toggle docked"});});
        $("#popupButton").click(function(){port.postMessage({command: "toggle popup"});});
        $("#timestamp").click(function(){port.postMessage({command: "toggle timestamp"});});
        $("#fontup").click(function(){port.postMessage({command: "fontup"});});
        $("#fontdown").click(function(){port.postMessage({command: "fontdown"});});
        $("#refresh").click(unblock);
        $("#chattit").mousedown(onMouseDown);
        $("#chatarea").keypress(keyHandler);
        $(window).resize(redraw);
        port.postMessage({command: "ready", subreddit: getSubreddit()});
        //redraw();
    });
});


// Get the subreddit path.
// ---------------------------------------------------------------------------------------------------------------------
function getSubreddit(){
    s = window.location.pathname.split("/");
    sub = "";
    i = 0;
    while(i < s.length && i < 3){
        sub += s[i] + "/";
        i += 1;
    }
    sub = sub.slice(0, sub.length - 1);     
    return sub;
}


// Scroll to the bottom of the chattit window.
// ---------------------------------------------------------------------------------------------------------------------
function scrollBottom()
{
    if(!scrollLock)
    {
        $("#chat").attr({scrollTop: $("#chat").attr("scrollHeight")});      
        scrollLock = false;
    }
}


// Redraw the chattit window.
// ---------------------------------------------------------------------------------------------------------------------
function redraw()
{
    //console.log("redraw");
    $("#chattit").css("width", chatWidth);
    $("#chattit").css("height", chatHeight);
    $("#chattit").css("top", chatY);
    $("#chattit").css("left", chatX);
    $("#chattit").css("border-radius", 8);
    $("#info").css("width", $("#chattit").innerWidth() - 8);
    $("#chat").css("width", $("#chattit").innerWidth() - 8);
    $("#chat").css("top", $("#info").css("bottom") + 4);
    $("#chat").css("height", $("#chattit").innerHeight() - ($("#chatarea").outerHeight() + $("#info").outerHeight() + 24));
    $("#chatarea").css("width", $("#chattit").innerWidth() - 23);
    $("body").css("width", $(window).width());  
    if(hidden)
    {
        $("#chattit").css("top", $(window).height() - 24);
        $("#chattit").css("left", $(window).width() - ($("#chattit").outerWidth() + 8));
    }      
    if(docked && !hidden)
    {
        $("#chattit").css("border-radius", 0);
        $("#chattit").css("height", $(window).height());
        $("#chattit").css("top", -1);
        $("#chattit").css("left", $(window).width() - $("#chattit").outerWidth());
        $("#chat").css("height", $("#chattit").innerHeight() - ($("#chatarea").outerHeight() + $("#info").outerHeight() + 24));
        $("body").css("width", $(window).width() - $("#chattit").outerWidth());        
        $("#chattit").css("width", chatWidth + 1);
    }
    scrollBottom();
}

// Block a user.
// ---------------------------------------------------------------------------------------------------------------------
function openUserPopup(username, hash)
{
    $("#userPopupName").html("<a href='http://www.reddit.com/user/" + username + "' target='_blank'>" + username + "</a>");
    $("#userPopupName").click(function(){$("#userPopup").hide();return true;});
    $("#userPopupHash").html("unique chattit hash: " + hash);
    $("#userPopupCancel").click(function(){$("#userPopup").hide();});
    $("#userPopupBlock").click(function()
    {
        $("#userPopup").hide();
        port.postMessage({command: "block", hash: hash});
        $("#userPopupBlock").unbind("click");
    });
    $("#userPopupMessageButton").click(function()
    {
        $("#userPopup").hide();
        port.postMessage({command: "send chat", chat: $("#userPopupMessage").val(), hash: hash});   
        $("#userPopupMessage").val("");
        $("#userPopupMessageButton").unbind("click");
    });
    $("#userPopup").css("left", $(window).width() / 2 - $("#userPopup").width() / 2);
    $("#userPopup").css("top", $(window).height() / 2 - $("#userPopup").height() / 2);
    $("#userPopup").show();
}

// Unblock all.
// ---------------------------------------------------------------------------------------------------------------------
function unblock()
{
    var doUnblock = confirm("Unblock everyone you've blocked?");
    if(doUnblock)
    {
        port.postMessage({command: "unblock"});
    }
}

// Print a line to the chattit window.
// ---------------------------------------------------------------------------------------------------------------------
function printf(string, color, weight, onclick)
{
    id = '' + parseInt(Math.random()*1000000);
    $("#chat").append("<span id='" + id + 
                      "' style='color:" + color + ";" +
                      "font-weight:" + weight + ";'" + 
                      ">" + string + "</span>");
    $("#" + id).click(function()
    {
        eval(onclick);
        return true;
    });
    if(timestamp)
    {
        $(".timestamp").show();
    }
    else
    {
        $(".timestamp").hide();
    }
    scrollBottom();
}


// Globals for mouse movement.
// ---------------------------------------------------------------------------------------------------------------------
var mouseStartX = 0;
var mouseStartY = 0;
var chatXStart = 0;
var chatYStart = 0;
var chatWidthStart = 0;
var chatHeightStart = 0;
var dragMode = "move";
var resizeLeft = false;
var resizeRight = false;
var resizeTop = false;
var resizeBottom = false;

function onMouseMove(e)
{
    diffx = e.clientX - mouseStartX;
    diffy = e.clientY - mouseStartY;
    newX = chatX;
    newY = chatY;
    newWidth = chatWidth;
    newHeight = chatHeight;
    if(dragMode == "resize")
    {
        if(resizeLeft)
        {
            newX = chatXStart + diffx;
            newWidth = chatWidthStart - diffx;
        }
        if(resizeRight)
        {
            newWidth = chatWidthStart + diffx;
        }
        if(resizeTop)
        {
            newY = chatYStart + diffy;
            newHeight = chatHeightStart - diffy;
        }
        if(resizeBottom)
        {
            newHeight = chatHeightStart + diffy;
        }
    }
    else
    {
        newX = chatXStart + diffx;
        newY = chatYStart + diffy;
    }
    port.postMessage({command: "set position", chatWidth: newWidth, chatHeight: newHeight, 
                      chatX: newX, chatY: newY});
}

function onMouseUp(e)
{
    $(document).unbind('mousemove');
    $(document).unbind('mouseup');
}

function onMouseDown(e)
{
    if(e.ctrlKey && !hidden)
    {
        dragMode = "move";
        if(docked)
        {
            dragMode = "resize";
        }
        resizeLeft = false;
        resizeRight = false;
        resizeTop = false;
        resizeBottom = false;
        $(document).mousemove(onMouseMove);
        $(document).mouseup(onMouseUp);
        mouseStartX = e.clientX;
        mouseStartY = e.clientY;
        
        chatXStart = chatX;
        chatYStart = chatY;
        chatWidthStart = chatWidth;
        chatHeightStart = chatHeight;
        if (e.offsetX < 10)
        {
            dragMode = 'resize';
            resizeLeft = true;
        }
        if (e.offsetX > chatWidth - 10)
        {
            dragMode = 'resize';
            resizeRight = true;
        }
        if (e.offsetY < 10)
        {
            dragMode = 'resize';
            resizeTop = true;
        }
        if (e.offsetY > chatHeight - 10)
        {
            dragMode = 'resize';
            resizeBottom = true;
        }
        return false;
    }
}


function getUserName()
{
    if($(".user")[0].innerHTML.indexOf('">register</a>') != -1)
    {
        return "";
    }
    return $(".user")[0].innerHTML.substr($(".user")[0].innerHTML.indexOf('http://www.reddit.com/user/') + 27, 
                                          $(".user")[0].innerHTML.indexOf('/"') - 
                                          $(".user")[0].innerHTML.indexOf('http://www.reddit.com/user/') - 27)
}


function keyHandler(e)
{
    if(e.keyCode == 13)
    {
        if($("#chatarea").val().indexOf("/i") == 0)
        {
            var emote = $("#chatarea").val().replace("/i", "");
            port.postMessage({command: "send emote", emote:emote});
        }
        else if($("#chatarea").val().indexOf("/name") == 0)
        {
            var desire = $("#chatarea").val().replace("/name", "");
            port.postMessage({command: "set user name", userName: desire});
        }
        else
        {
            port.postMessage({command: "send chat", chat: $("#chatarea").val()});
        }
        $("#chatarea").val("");    
        return false;
    }
    $("#chatarea").val($("#chatarea").val().substr(0, 511));    
    return true;
}













