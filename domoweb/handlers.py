#!/usr/bin/env python
from tornado import web, websocket, gen
from tornado.options import options
from tornado.web import RequestHandler, StaticFileHandler
from tornado.gen import Return
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient

from domoweb.models import to_json, Section, Widget, DataType, WidgetInstance, WidgetInstanceOption, WidgetInstanceSensor, WidgetInstanceCommand, WidgetInstanceDevice, SectionParam, Sensor, Theme
from domoweb.forms import WidgetInstanceForms, WidgetStyleForm

import os
import json
import logging
logger = logging.getLogger('domoweb')

import zmq
from domogikmq.pubsub.subscriber import MQAsyncSub
from domogikmq.reqrep.client import MQSyncReq
from domogikmq.message import MQMessage

import traceback

socket_connections = []

class MainHandler(RequestHandler):
    def get(self, id):
        if not id:
            id = 1
        section = Section.get(id)
        packs = Widget.getSectionPacks(section_id=id)
        params = Section.getParamsDict(id)
        sections = Section.getTree()
        self.render('base.html',
            section = section,
            params = params,
            packs = packs,
            sections = sections,
            )

class ConfigurationHandler(RequestHandler):
    def get(self):
        action = self.get_argument('action', None)
        id = self.get_argument('id', None)
        if action=='widget':
            instance = WidgetInstance.get(id);
            forms = WidgetInstanceForms(instance=instance)
            self.render('widgetConfiguration.html', instance=instance, forms=forms)
        elif action=='section':
            section = Section.get(id)
            params = Section.getParamsDict(id)
            themeWidgetsStyle = Theme.getParamsDict(section.theme.id, ["widget"])
            options = SectionParam.getSection(section_id=id)
            dataOptions = dict([(r.key, r.value) for r in options])
            widgetForm = WidgetStyleForm(data=dataOptions, prefix='params')
            backgrounds = [{'type':'uploaded', 'href': 'backgrounds/thumbnails/%s'%f, 'value': 'backgrounds/%s'%f} for f in os.listdir('/var/lib/domoweb/backgrounds') if any(f.lower().endswith(x) for x in ('.jpeg', '.jpg','.gif','.png'))]
            themeSectionStyle = Theme.getParamsDict(section.theme.id, ["section"])
            if 'SectionBackgroundImage' in themeSectionStyle:
                href = "%s/thumbnails/%s" % (os.path.dirname(themeSectionStyle['SectionBackgroundImage']), os.path.basename(themeSectionStyle['SectionBackgroundImage']))
                backgrounds.insert(0, {'type': 'theme', 'href': href, 'value': themeSectionStyle['SectionBackgroundImage']})
            self.render('sectionConfiguration.html', section=section, params=params, backgrounds=backgrounds, widgetForm=widgetForm, themeWidgetsStyle=themeWidgetsStyle)
        elif action=='addsection':
            self.render('sectionAdd.html')

    def post(self):
        action = self.get_argument('action', None)
        id = self.get_argument('id', None)
        if action=='widget':
            instance = WidgetInstance.get(id);
            forms = WidgetInstanceForms(instance=instance, handler=self)
            if forms.validate():
                forms.save();
                if (instance.widget.default_style):
                    d = WidgetInstance.getFullOptionsDict(id=id)
                else:
                    d = WidgetInstance.getOptionsDict(id=id)
                jsonoptions = {'instance_id':id, 'options':d}
                d = WidgetInstanceSensor.getInstanceDict(instance_id=id)
                jsonsensors = {'instance_id':id, 'sensors':d}
                d = WidgetInstanceCommand.getInstanceDict(instance_id=id)
                jsoncommands = {'instance_id':id, 'commands':d}
                d = WidgetInstanceDevice.getInstanceDict(instance_id=id)
                jsondevices = {'instance_id':id, 'devices':d}
                for socket in socket_connections:
                    socket.sendMessage(['widgetinstance-options', jsonoptions]);
                    socket.sendMessage(['widgetinstance-sensors', jsonsensors]);
                    socket.sendMessage(['widgetinstance-commands', jsoncommands]);
                    socket.sendMessage(['widgetinstance-devices', jsondevices]);
                self.write("{success:true}")
            else:
                self.render('widgetConfiguration.html', instance=instance, forms=forms)
        elif action=='section':
            Section.update(id, self.get_argument('sectionName'), self.get_argument('sectionDescription', None))
            section = Section.get(id)
            themeSectionStyle = Theme.getParamsDict(section.theme.id, ["section"])

            widgetForm = WidgetStyleForm(handler=self, prefix='params')

            for p, v in self.request.arguments.iteritems():
                if p.startswith( 'params' ):
                    if v[0] and not (p[0] == 'params-SectionBackgroundImage' and v[0] == themeSectionStyle['SectionBackgroundImage']):
                        SectionParam.saveKey(section_id=id, key=p[7:], value=v[0])
                    else:
                        SectionParam.delete(section_id=id, key=p[7:])

            # Send section updated params
            json = to_json(Section.get(id))
            json['params'] = Section.getParamsDict(id)
            WSHandler.sendAllMessage(['section-params', json])

            self.write("{success:true}")
        elif action=='addsection':
            s = Section.add(id, self.get_argument('sectionName'), self.get_argument('sectionDescription'))
            for p, v in self.request.arguments.iteritems():
                if p.startswith( 'params' ):
                    if v[0]:
                        SectionParam.saveKey(section_id=s.id, key=p[7:], value=v[0])
                        print s.id, p[7:], v[0]

            json = to_json(s)
            WSHandler.sendAllMessage(['section-added', json])
            self.write("{success:true}")

class WSHandler(websocket.WebSocketHandler):
    def open(self):
        socket_connections.append(self)
    def on_close(self):
        socket_connections.remove(self)

    @gen.coroutine
    def on_message(self, message):
        logger.info("WS: Received message %s" % message)
        jsonmessage = json.loads(message)

        if (jsonmessage[0] == 'sensor-gethistory'): 
            data = yield self.WSSensorGetHistory(jsonmessage[1])
        elif(jsonmessage[0] == 'sensor-getlast'): 
            data = yield self.WSSensorGetLast(jsonmessage[1])
        else:
            data = {
                'section-get' : self.WSSectionGet,
                'section-getall' : self.WSSectionGetall,
                'section-gettree' : self.WSSectionGettree,
                'section-remove' : self.WSSectionRemove,
                'widget-getall' : self.WSWidgetsGetall,
                'widgetinstance-getsection' : self.WSWidgetInstanceGetsection,
                'widgetinstance-getoptions' : self.WSWidgetInstanceGetoptions,
                'widgetinstance-getsensors' : self.WSWidgetInstanceGetsensors,
                'widgetinstance-getcommands' : self.WSWidgetInstanceGetcommands,
                'widgetinstance-getdevices' : self.WSWidgetInstanceGetdevices,
                'datatype-getall' : self.WSDatatypesGetall,
                'command-send' : self.WSCommandSend,
                'widgetinstance-add' : self.WSWidgetInstanceAdd,
                'widgetinstance-location' : self.WSWidgetInstanceLocation,
                'widgetinstance-remove' : self.WSWidgetInstanceRemove,
            }[jsonmessage[0]](jsonmessage[1])
        if (data):
            # If the modif is global we send the result to all listeners
            if (jsonmessage[0] in ['widgetinstance-add', 'widgetinstance-location', 'widgetinstance-remove', 'section-remove']):
                WSHandler.sendAllMessage(data)
            else:
                self.sendMessage(data)

    def WSSectionGet(self, data):
        section = Section.get(data['id'])
        widgets = Widget.getSection(section_id=data['id'])
        instances = WidgetInstance.getSection(section_id=data['id'])
        j = to_json(section)
        j['params'] = Section.getParamsDict(data['id'])
        j["widgets"] = to_json(widgets)
        j["instances"] = to_json(instances)
        for index, item in enumerate(instances):
            if item.widget:
                j['instances'][index]["widget"] = to_json(item.widget)
            try:
                optionsdict = WidgetInstance.getOptionsDict(id=item.id)
                j['instances'][index]["options"] = optionsdict
            except:
                logger.error("Error while getting options for a widget instance. Maybe you delete a widget folder but it is still defined in database? Error: {0}".format(traceback.format_exc()))

        return ['section-details', j]

    def WSSectionGetall(self, data):
        root = Section.getAll()
        j = to_json(sections)
        return ['section-list', j]

    def WSSectionGettree(self, data):
        root = Section.getTree()
        j = to_json(root)
        j["childs"] = self.json_childs(root, 1)
        j["level"] = 0
        return ['section-tree', j]

    def json_childs(self, section, level):
        res = []
        if section._childrens:
            for child in section._childrens:
                c = to_json(child)
                c["childs"] = self.json_childs(child, level+1)
                c["level"] = level
                res.append(c)
        return res

    def WSSectionRemove(self, data):
        i = Section.delete(data['section_id'])
        json = to_json(i)
        return ['section-removed', json];

    def WSWidgetsGetall(self, data):
        widgets = Widget.getAll()
        return ['widget-list', to_json(widgets)]

    def WSWidgetInstanceAdd(self, data):
        i = WidgetInstance.add(section_id=data['section_id'], widget_id=data['widget_id'], x=data['x'], y=data['y'])
        json = to_json(i)
        json["widget"] = to_json(i.widget)
        return ['widgetinstance-added', json];

    def WSWidgetInstanceRemove(self, data):
        i = WidgetInstance.delete(data['instance_id'])
        json = to_json(i)
        json["widget"] = to_json(i.widget)
        return ['widgetinstance-removed', json];

    def WSWidgetInstanceLocation(self, data):
        i = WidgetInstance.updateLocation(id=data['instance_id'], x=data['x'], y=data['y'])
        json = to_json(i)
        json["widget"] = to_json(i.widget)
        return ['widgetinstance-moved', json];

    def WSWidgetInstanceGetsection(self, data):
        r = WidgetInstance.getSection(section_id=data['section_id'])
        json = {'section_id':data['section_id'], 'instances':to_json(r)}
        for index, item in enumerate(r):
            if item.widget:
                json['instances'][index]["widget"] = to_json(item.widget)
            else: #remove instance
                logger.info("Section: Widget '%s' not installed, removing instance" % item.widget_id)
                WidgetInstance.delete(item.id)
                del json['instances'][index]
        return ['widgetinstance-sectionlist', json];

    def WSWidgetInstanceGetoptions(self, data):
        i = WidgetInstance.get(data['instance_id'])
        if (i.widget.default_style):
            d = WidgetInstance.getFullOptionsDict(id=data['instance_id'])
        else:
            d = WidgetInstance.getOptionsDict(id=data['instance_id'])
        json = {'instance_id':data['instance_id'], 'options':d}
        return ['widgetinstance-options', json];

    def WSWidgetInstanceGetsensors(self, data):
        d = WidgetInstanceSensor.getInstanceDict(instance_id=data['instance_id'])
        json = {'instance_id':data['instance_id'], 'sensors':d}
        return ['widgetinstance-sensors', json];

    def WSWidgetInstanceGetcommands(self, data):
        d = WidgetInstanceCommand.getInstanceDict(instance_id=data['instance_id'])
        json = {'instance_id':data['instance_id'], 'commands':d}
        return ['widgetinstance-commands', json];

    def WSWidgetInstanceGetdevices(self, data):
        d = WidgetInstanceDevice.getInstanceDict(instance_id=data['instance_id'])
        json = {'instance_id':data['instance_id'], 'devices':d}
        return ['widgetinstance-devices', json];

    def WSDatatypesGetall(self, data):
        datatypes =dict ((o.id, json.loads(o.parameters)) for o in DataType.getAll())
        return ['datatype-list', datatypes]

    def WSCommandSend(self, data):
        cli = MQSyncReq(zmq.Context())
        msg = MQMessage()
        msg.set_action('cmd.send')
        msg.add_data('cmdid', data['command_id'])
        msg.add_data('cmdparams', data['parameters'])
        return cli.request('xplgw', msg.get(), timeout=10).get()

    @gen.coroutine
    def WSSensorGetHistory(self, data):
        url = '%s/sensorhistory/id/%d/from/%d/to/%d/interval/%s/selector/avg' % (options.rest_url, data['id'],data['from'],data['to'],data['interval'])
        logger.info("REST Call : %s" % url)
        http = AsyncHTTPClient()
        response = yield http.fetch(url)
        j = json_decode(response.body)
        try:
            history = j['values']
        except ValueError:
            history = []
        json = {'caller':data['caller'], 'id':data['id'], 'history':history}
        raise Return(['sensor-history', json])

    @gen.coroutine
    def WSSensorGetLast(self, data):
        url = '%s/sensorhistory/id/%d/last/%d' % (options.rest_url, data['id'],data['count'])
        logger.info("REST Call : %s" % url)
        http = AsyncHTTPClient()
        response = yield http.fetch(url)
        j = json_decode(response.body)
        try:
            history = j['values']
        except ValueError:
            history = []
        json = {'caller':data['caller'], 'id':data['id'], 'history':history}
        raise Return(['sensor-history', json])

    def sendMessage(self, content):
        data=json.dumps(content)
        logger.info("WS: Sending message %s" % data)
        self.write_message(data)

    @classmethod
    def sendAllMessage(cls, content):
        data=json.dumps(content)
        logger.info("WS: Sending message %s" % data)
        for socket in socket_connections:
            socket.write_message(data)

class NoCacheStaticFileHandler(web.StaticFileHandler):
    def set_extra_headers(self, path):
        # Disable cache
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')

class MQHandler(MQAsyncSub):
    def __init__(self):
        MQAsyncSub.__init__(self, zmq.Context(), 'test', ['device-stats'])

    def on_message(self, msgid, content):
        #logger.info(u"MQ: New pub message {0}".format(msgid))
        #logger.info(u"MQ: {0}".format(content))

        if isinstance(content["stored_value"], list):
            content["stored_value"] = content["stored_value"][0]
            logger.error(u"MQ: PATCH for issue #1976")

        # If sensor stat, we update the sensor last value
        if msgid == 'device-stats':
            Sensor.update(content["sensor_id"], content["timestamp"], content["stored_value"])

        WSHandler.sendAllMessage([msgid, content])

class UploadHandler(RequestHandler):
    def post(self):
        from PIL import Image
        original_fname = self.get_argument('qqfile', None)
        fileName, fileExtension = os.path.splitext(original_fname)
        tmpFileName = fileName
        i = 0
        while os.path.isfile("/var/lib/domoweb/backgrounds/%s%s" % (tmpFileName , fileExtension)):
            i += 1
            tmpFileName = "%s_%d" % (fileName, i)

        final_fname = "/var/lib/domoweb/backgrounds/%s%s" % (tmpFileName , fileExtension)
        output_file = open(final_fname, 'wb')
        output_file.write(self.request.body)
        output_file = open(final_fname, 'r+b')

        # Create Thumbnail
        basewidth = 128
        img = Image.open(output_file)
        wpercent = (basewidth / float(img.size[0]))
        hsize = int((float(img.size[1]) * float(wpercent)))
        img.thumbnail((basewidth, hsize), Image.ANTIALIAS)
        img.save("/var/lib/domoweb/backgrounds/thumbnails/%s%s" % (tmpFileName , fileExtension), "JPEG")
        self.finish("{success:true}")

class MultiStaticFileHandler(StaticFileHandler):
    def get(self, ns, lang, file):
        path = "%s/locales/%s/%s" % (ns, lang, file)
        return super(MultiStaticFileHandler, self).get(path)
