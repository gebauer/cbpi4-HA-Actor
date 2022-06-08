import logging
import asyncio
from cbpi.api import *

import requests


logger = logging.getLogger(__name__)

@parameters([
    Property.Select(label="Check Certificate", options=['YES','NO'], description="Enable or disable TLS certificate checking. This setting has no impact for unencrypted connections"),
    Property.Number(label="Request Timeout", configurable=True, description="HTTP request timeout in seconds (default 5)", default_value=5),

    Property.Text(label="Base API entry point", configurable=True, description="REST Api entry point. Must include a uri scheme (http://yourhome:8123/api/...)"),

    Property.Text(label="Entity id", configurable=True, description="Entity id of the actor in HA (e.g. switch.pumpe)"),

    Property.Text(label="Authorization Token", configurable=True, description="Authorization token for HA API. E.g. ACBS§RSDF#S§%ASDF.sdfs..."),

    Property.Select(label="Continuous Mode", options=['YES','NO'], description="Enable this if the remote url should be refreshed periodically even if our local actor state hasn't changed"),
    Property.Number(label="Continuous Interval", configurable=True, description="Refresh interval in seconds used in continuous mode"),
    Property.Number(label="EasyPWM sampling time", configurable=True,  description="Time in seconds for power base interval (Default:5)")
    ])


class HAActor(CBPiActor):

    @action("Set Power", parameters=[Property.Number(label="Power", configurable=True, description="Power Setting [0-100]")])
    async def setpower(self, Power=100, **kwargs):
        self.power = int(Power)
        if self.power < 0:
            self.power = 0
        if self.power > 100:
            self.power = 100
        await self.set_power(self.power)

    async def on_start(self):
        self.power = None

        self.request_session = requests.Session()

        if self.props.get("Check Certificate", "YES") == "YES":
            self.request_session.verify = True
        else:
            self.request_session.verify = False

        self.base_url = self.props.get("Base API entry point")
        self.entity = self.props.get("Entity id")
        self.domain, self.device = self.entity.split('.')

        self.html_headers = {}
        if self.props.get("Authorization Token") != "":
            self.html_headers["Authorization"] = "Bearer {}".format(self.props.get("Authorization Token"))
        self.html_headers["Content-Type"] = "application/json"

        self.sampleTime = int(self.props.get("EasyPWM sampling time", 5))

        self.continuous_interval = float(self.props.get("Continuous Interval", 5))
        self.request_session.timeout = float(self.props.get("Request Timeout", 5))

        self.state = False

    async def on(self, power=None):
        if power is not None:
            self.power = power
        else:
            self.power = 100
        self.state = True

    async def off(self):
        endpoint = self.base_url.strip('/')+'/services/'+self.domain.strip('/')+'/turn_off'
        payload = "{{\"entity_id\": \"{}\"}}".format(self.entity)
        response = self.request_session.post(endpoint, data=payload, headers=self.html_headers)
        logger.info("Switching actor off")
        self.state = False

    def get_state(self):
        return self.state

    async def run(self):
        while self.running is True:
            if self.state is True:
                heating_time = self.sampleTime * (self.power / 100)
                wait_time = self.sampleTime - heating_time
                if heating_time > 0:
                    # logging.info("Heating Time: {}".format(heating_time))
                    endpoint = self.base_url.strip('/')+'/services/'+self.domain.strip('/')+'/turn_on'
                    payload = "{{\"entity_id\": \"{}\"}}".format(self.entity)
                    response = self.request_session.post(endpoint, data=payload, headers=self.html_headers)
                    logger.info("Setting Actor on for {} s".format(heating_time))

                    await asyncio.sleep(heating_time)
                if wait_time > 0:
                    endpoint = self.base_url.strip('/')+'/services/'+self.domain.strip('/')+'/turn_off'
                    payload = "{{\"entity_id\": \"{}\"}}".format(self.entity)
                    response = self.request_session.post(endpoint, data=payload, headers=self.html_headers)
                    logger.info("Setting Actor off for {} s".format(wait_time))
                    await asyncio.sleep(wait_time)
            else:
                await asyncio.sleep(1)
        pass

    async def set_power(self, power):
        self.power = round(power)
        if self.state is True:
            await self.on(power)
        else:
            await self.off()
        await self.cbpi.actor.actor_update(self.id, power)
        pass


def setup(cbpi):
    cbpi.plugin.register("HomeAssistant Actor", HAActor)
