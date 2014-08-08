var express = require('express'),
    _ = require('underscore'),
    q = require('q'),
    sqlite = require('sqlite3');

var app = express();

app.use(express.bodyParser());
app.use(express.cookieParser());

app.get('/', function(req, res) {
    res.sendfile("index.html");
});

app.get('/js/pi-timer.js', function(req, res) {
    res.sendfile("js/pi-timer.js");
});

app.get('/images/sprinkler.jpg', function(req, res) {
    res.sendfile("images/sprinkler.jpg");
});

var db = new sqlite.Database("/var/lib/pi-timer/db.sqlite");
var fetchRows = function() {
    var deferred = q.defer();
    params = Array.prototype.slice.call(arguments, 0);
    params.push(function(err, rows) {
        if (err) {
            deferred.reject(err);
        } else {
            deferred.resolve(rows);
        }
    });
    db.all.apply(db, params);
    return deferred.promise;
};

app.get('/data', function(req, res) {
    var returnData = {
        devices: {}
    };
    fetchRows("SELECT device_id, group_id, type, display_name, pin FROM devices").then(function(devices) {
            var deferreds = _.map(devices, function(device) {
                returnData.devices[device.device_id] = device;
                return fetchRows("SELECT timestamp, enabled FROM device_history WHERE device = ? ORDER BY timestamp", device.device_id).then(function(history) {
                    returnData.devices[device.device_id].history = history;
                    return fetchRows("SELECT timestamp, start_time, duration, min_duration FROM device_schedule WHERE device = ? ORDER BY timestamp", device.device_id).then(function(schedule) {
                        returnData.devices[device.device_id].schedule = schedule;
                    });
                });
            });
            return q.all(deferreds);
        }).then(function() {
            res.json(returnData);
        },
        function(err) {
            res.send(500, err);
        });
});

app.listen(80);
console.log("Listening on port 80");

exports.app = app;
