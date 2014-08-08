/** @jsx React.DOM */

var toDate = function(sec) {
    var d = new Date();
    d.setTime(sec * 1000);
    return d;
};

var PiTimerView = React.createClass({
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
            return <div>Loading...</div>;
        }

        var now = new Date();

        return <div>
            <div style={styles.updateTime}>
                <span>Last updated: {""+this.state.lastFetch}</span>
                {this.state.loading && <span>(Loading...)</span>}
            </div>
            {_.map(this.state.data.devices, function(device) {
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
                                <li>Ran on {runStart.toLocaleString()} for {Math.floor(entry.timestamp - runStart)/1000} seconds.</li>);
                            runStart = null;
                        }
                    } else {
                        if (runStart === null) {
                            runStart = entry.timestamp;
                        }
                    }
                });
                history.reverse();

                var nextRunView = <span>No upcoming events on calendar.</span>;
                if (runStart !== null) {
                    nextRunView = <span style={styles.currentlyRunning}>Device is currently running. (Started {runStart.toLocaleTimeString()})</span>;
                } else if (nextRun) {
                    nextRunView = <span>{nextRun.start_time.toLocaleString()} for {nextRun.duration/1000} seconds.</span>;
                }
                return <div style={styles.deviceCard}>
                    <div style={styles.iconWrapper}>
                        <img src={"/images/" + device.type + ".jpg"} style={styles.iconImage} />
                        <div style={styles.iconLabel}>device:{device.device_id} / {device.group_id}</div>
                    </div>
                    <div style={styles.deviceBody}>
                      <div style={styles.displayName}>{device.display_name}</div>
                      <div style={styles.nextRun}>
                        <span style={styles.nextRunLabel}>Next scheduled run:</span>
                        {nextRunView}
                      </div>
                      <ul style={styles.historyList}>
                        {history}
                      </ul>
                    </div>
                </div>;
            })}
        </div>;
    }
});

React.renderComponent(
    <PiTimerView />,
    document.getElementById('body'));
console.log("Loaded!", React);
