/** @jsx React.DOM */

var toDate = function(sec) {
    var d = new Date();
    d.setTime(sec * 1000);
    return d;
};

var PiTimerView = React.createClass({displayName: 'PiTimerView',
    getInitialState: function() {
        return {
            loading: true,
            lastFetch: null,
            data: null
        };
    },

    loadData: function() {
        var self = this;
        this.setState({
            loading: true
        });
        var xmlhttp = new XMLHttpRequest();
        xmlhttp.onreadystatechange = function() {
            if (xmlhttp.readyState === 4 && xmlhttp.status === 200) {
                var data = JSON.parse(xmlhttp.responseText);
                // Convert timestamps to dates
                _.each(data.devices, function(device) {
                    _.each(device.history, function(entry) {
                        entry.timestamp = toDate(entry.timestamp);
                    });
                    _.each(device.schedule, function(entry) {
                        entry.timestamp = toDate(entry.timestamp);
                        entry.start_time = toDate(entry.start_time);
                    });
                });
                self.setState({
                    loading: false,
                    lastFetch: new Date(),
                    data: data
                });
            }
        }
        xmlhttp.open("GET", "/data", true);
        xmlhttp.send();
    },

    componentDidMount: function() {
        var self = this;
        this.loadData();
        window.setInterval(function() { self.loadData(); }, 60000);
    },

    render: function() {
        var styles = {
            updateTime: {
                color: "#aaa",
                fontSize: "14px",
                textAlign: "center"
            },
            deviceCard: {
                backgroundColor: "#cfb",
                borderRadius: "20px",
                margin: "25px",
                padding: "15px"
            },
            iconWrapper: {
                width: "137px",
                display: "inline-block",
                verticalAlign: "top"
            },
            iconImage: {
                width: "137px",
                height: "140px"
            },
            iconLabel: {
                color: "#444",
                marginTop: "5px",
                textAlign: "center"
            },
            deviceBody: {
                display: "inline-block",
                marginLeft: "10px",
                verticalAlign: "top"
            },
            displayName: {
                color: "#003",
                fontSize: "30px",
                fontWeight: "bold",
                textShadow: "-2px 2px 1px #fff"
            },
            nextRun: {
                color: "#003",
                fontSize: "20px",
                marginTop: "10px"
            },
            nextRunLabel: {
                fontWeight: "bold",
                marginRight: "20px"
            },
            historyList: {
                height: "80px",
                overflowY: "auto"
            }
        };

        if (!this.state.data) {
            return React.DOM.div(null, "Loading...");
        }

        var now = new Date();

        return React.DOM.div(null, 
            React.DOM.div({style: styles.updateTime}, 
                React.DOM.span(null, "Last updated: ", ""+this.state.lastFetch), 
                this.state.loading && React.DOM.span(null, "(Loading...)")
            ), 
            _.map(this.state.data.devices, function(device) {
                var nextRun = null;
                _.each(device.schedule, function(entry) {
                    if (entry.start_time >= now) {
                        if (!nextRun || entry.start_time < nextRun.start_time) {
                            nextRun = entry;
                        }
                    }
                });
                var history = [];
                var runStart = null;
                _.each(device.history, function(entry) {
                    if (entry.enabled === 0) {
                        if (runStart !== null) {
                            history.push(
                                React.DOM.li(null, "Ran on ", runStart.toLocaleString(), " for ", Math.floor(entry.timestamp - runStart)/1000, " seconds."));
                            runStart = null;
                        }
                    } else {
                        if (runStart === null) {
                            runStart = entry.timestamp;
                        }
                    }
                });
                history.reverse();

                var nextRunView = React.DOM.span(null, "No upcoming events on calendar.");
                if (runStart !== null) {
                    nextRunView = React.DOM.span({style: styles.currentlyRunning}, "Device is currently running. (Started ", runStart.toLocaleTimeString(), ")");
                } else if (nextRun) {
                    nextRunView = React.DOM.span(null, nextRun.start_time.toLocaleString(), " for ", nextRun.duration/1000, " seconds.");
                }
                return React.DOM.div({style: styles.deviceCard}, 
                    React.DOM.div({style: styles.iconWrapper}, 
                        React.DOM.img({src: "/images/" + device.type + ".jpg", style: styles.iconImage}), 
                        React.DOM.div({style: styles.iconLabel}, "device:", device.device_id, " / ", device.group_id)
                    ), 
                    React.DOM.div({style: styles.deviceBody}, 
                      React.DOM.div({style: styles.displayName}, device.display_name), 
                      React.DOM.div({style: styles.nextRun}, 
                        React.DOM.span({style: styles.nextRunLabel}, "Next scheduled run:"), 
                        nextRunView
                      ), 
                      React.DOM.ul({style: styles.historyList}, 
                        history
                      )
                    )
                );
            })
        );
    }
});

React.renderComponent(
    PiTimerView(null),
    document.getElementById('body'));
console.log("Loaded!", React);
