import os
import random
import logging
import math

from golem.task.TaskState import SubtaskStatus

from examples.gnr.RenderingEnvironment import PBRTEnvironment
from examples.gnr.RenderingDirManager import getTestTaskPath
from examples.gnr.RenderingTaskState import RendererDefaults, RendererInfo, RenderingTaskDefinition
from examples.gnr.task.SceneFileEditor import regeneratePbrtFile
from examples.gnr.task.GNRTask import GNROptions, GNRTaskBuilder
from examples.gnr.task.RenderingTask import RenderingTask, RenderingTaskBuilder
from examples.gnr.task.RenderingTaskCollector import RenderingTaskCollector
from examples.gnr.ui.PbrtDialog import PbrtDialog
from examples.gnr.customizers.PbrtDialogCustomizer import PbrtDialogCustomizer


logger = logging.getLogger(__name__)

##############################################
def buildPBRTRendererInfo():
    defaults = RendererDefaults()
    defaults.outputFormat       = "EXR"
    defaults.mainProgramFile    = os.path.normpath(os.path.join(os.environ.get('GOLEM'), 'examples/tasks/pbrtTask.py'))
    defaults.minSubtasks        = 4
    defaults.maxSubtasks        = 200
    defaults.defaultSubtasks    = 60


    renderer                = RendererInfo("PBRT", defaults, PbrtTaskBuilder, PbrtDialog, PbrtDialogCustomizer, PbrtRendererOptions)
    renderer.outputFormats  = [ "BMP", "EPS", "EXR", "GIF", "IM", "JPEG", "PCX", "PDF", "PNG", "PPM", "TIFF" ]
    renderer.sceneFileExt    = [ "pbrt" ]
    renderer.getTaskNumFromPixels = getTaskNumFromPixels
    renderer.getTaskBoarder = getTaskBoarder

    return renderer

##############################################
class PbrtRendererOptions( GNROptions):
    #######################
    def __init__(self):
        self.pbrtPath = ''
        self.pixelFilter = "mitchell"
        self.samplesPerPixelCount = 32
        self.algorithmType = "lowdiscrepancy"
        self.filters = [ "box", "gaussian", "mitchell", "sinc", "triangle" ]
        self.pathTracers = [ "adaptive", "bestcandidate", "halton", "lowdiscrepancy", "random", "stratified" ]

    #######################
    def addToResources(self, resources):
        if os.path.isfile(self.pbrtPath):
            resources.add(os.path.normpath(self.pbrtPath))
        return resources

    #######################
    def removeFromResources(self, resources):
        if os.path.normpath(self.pbrtPath) in resources:
            resources.remove(os.path.normpath(self.pbrtPath))
        return resources

##############################################
class PbrtGNRTaskBuilder(GNRTaskBuilder):
    def build(self):
        if isinstance(self.taskDefinition, RenderingTaskDefinition):
            rtd = self.taskDefinition
        else:
            rtd = self.__translateTaskDefinition()

        pbrtTaskBuilder = PbrtTaskBuilder(self.client_id, rtd, self.root_path)
        return pbrtTaskBuilder.build()

    def __translateTaskDefinition(self):
        rtd = RenderingTaskDefinition()
        rtd.task_id = self.taskDefinition.task_id
        rtd.fullTaskTimeout = self.taskDefinition.fullTaskTimeout
        rtd.subtask_timeout = self.taskDefinition.subtask_timeout
        rtd.minSubtaskTime = self.taskDefinition.minSubtaskTime
        rtd.resources = self.taskDefinition.resources
        rtd.estimatedMemory = self.taskDefinition.estimatedMemory
        rtd.totalSubtasks = self.taskDefinition.totalSubtasks
        rtd.optimizeTotal = self.taskDefinition.optimizeTotal
        rtd.mainProgramFile = self.taskDefinition.mainProgramFile
        rtd.taskType = self.taskDefinition.taskType
        rtd.verificationOptions = self.taskDefinition.verificationOptions

        rtd.resolution = self.taskDefinition.options.resolution
        rtd.renderer = self.taskDefinition.taskType
        rtd.mainSceneFile = self.taskDefinition.options.mainSceneFile
        rtd.resources.add(rtd.mainSceneFile)
        rtd.outputFile = self.taskDefinition.options.outputFile
        rtd.outputFormat = self.taskDefinition.options.outputFormat
        rtd.rendererOptions = PbrtRendererOptions()
        rtd.rendererOptions.pixelFilter = self.taskDefinition.options.pixelFilter
        rtd.rendererOptions.algorithmType = self.taskDefinition.options.algorithmType
        rtd.rendererOptions.samplesPerPixelCount = self.taskDefinition.options.samplesPerPixelCount
        rtd.rendererOptions.pbrtPath = self.taskDefinition.options.pbrtPath
        return rtd



##############################################
class PbrtTaskBuilder(RenderingTaskBuilder):
    #######################
    def build(self):
        mainSceneDir = os.path.dirname(self.taskDefinition.mainSceneFile)

        pbrtTask = PbrtRenderTask(self.client_id,
                                   self.taskDefinition.task_id,
                                   mainSceneDir,
                                   self.taskDefinition.mainProgramFile,
                                   self._calculateTotal(buildPBRTRendererInfo(), self.taskDefinition),
                                   20,
                                   4,
                                   self.taskDefinition.resolution[ 0 ],
                                   self.taskDefinition.resolution[ 1 ],
                                   self.taskDefinition.rendererOptions.pixelFilter,
                                   self.taskDefinition.rendererOptions.algorithmType,
                                   self.taskDefinition.rendererOptions.samplesPerPixelCount,
                                   self.taskDefinition.rendererOptions.pbrtPath,
                                   "temp",
                                   self.taskDefinition.mainSceneFile,
                                   self.taskDefinition.fullTaskTimeout,
                                   self.taskDefinition.subtask_timeout,
                                   self.taskDefinition.resources,
                                   self.taskDefinition.estimatedMemory,
                                   self.taskDefinition.outputFile,
                                   self.taskDefinition.outputFormat,
                                   self.root_path
                                 )

        return self._setVerificationOptions(pbrtTask)

    def _setVerificationOptions(self, newTask):
        newTask = RenderingTaskBuilder._setVerificationOptions(self, newTask)
        if newTask.advanceVerification:
            boxX = min(newTask.verificationOptions.boxSize[0], newTask.taskResX)
            boxY = min(newTask.verificationOptions.boxSize[1], newTask.taskResY)
            newTask.boxSize = (boxX, boxY)
        return newTask

    #######################
    def _calculateTotal(self, renderer, definition):

        if (not definition.optimizeTotal) and (renderer.defaults.minSubtasks <= definition.totalSubtasks <= renderer.defaults.maxSubtasks):
            return definition.totalSubtasks

        taskBase = 1000000
        allOp = definition.resolution[0] * definition.resolution[1] * definition.rendererOptions.samplesPerPixelCount
        return max(renderer.defaults.minSubtasks, min(renderer.defaults.maxSubtasks, allOp / taskBase))

def countSubtaskReg(totalTasks, subtasks, resX, resY):
    nx = totalTasks * subtasks
    ny = 1
    while (nx % 2 == 0) and (2 * resX * ny < resY * nx):
        nx /= 2
        ny *= 2
    taskResX = float(resX) / float(nx)
    taskResY = float(resY) / float(ny)
    return nx, ny, taskResX, taskResY

##############################################
class PbrtRenderTask(RenderingTask):

    #######################
    def __init__(self,
                  client_id,
                  task_id,
                  mainSceneDir,
                  mainProgramFile,
                  totalTasks,
                  numSubtasks,
                  num_cores,
                  resX,
                  resY,
                  pixelFilter,
                  sampler,
                  samplesPerPixel,
                  pbrtPath,
                  outfilebasename,
                  sceneFile,
                  fullTaskTimeout,
                  subtask_timeout,
                  taskResources,
                  estimatedMemory,
                  outputFile,
                  outputFormat,
                  root_path,
                  returnAddress = "",
                  returnPort = 0,
                  key_id = ""
                 ):


        RenderingTask.__init__(self, client_id, task_id, returnAddress, returnPort, key_id,
                                PBRTEnvironment.getId(), fullTaskTimeout, subtask_timeout,
                                mainProgramFile, taskResources, mainSceneDir, sceneFile,
                                totalTasks, resX, resY, outfilebasename, outputFile, outputFormat,
                                root_path, estimatedMemory)

        self.collectedFileNames = set()

        self.numSubtasks        = numSubtasks
        self.num_cores           = num_cores

        try:
            with open(sceneFile) as f:
                self.sceneFileSrc = f.read()
        except Exception, err:
            logger.error("Wrong scene file: {}".format(str(err)))
            self.sceneFileSrc = ""

        self.resX               = resX
        self.resY               = resY
        self.pixelFilter        = pixelFilter
        self.sampler            = sampler
        self.samplesPerPixel    = samplesPerPixel
        self.pbrtPath           = pbrtPath
        self.nx, self.ny, self.taskResX, self.taskResY = countSubtaskReg(self.totalTasks, self.numSubtasks, self.resX, self.resY)

    #######################
    def queryExtraData(self, perfIndex, num_cores = 0, client_id = None):
        if not self._acceptClient(client_id):
            logger.warning(" Client {} banned from this task ".format(client_id))
            return None


        startTask, endTask = self._getNextTask(perfIndex)
        if startTask is None or endTask is None:
            logger.error("Task already computed")
            return None

        if num_cores == 0:
            num_cores = self.num_cores

        workingDirectory = self._getWorkingDirectory()
        sceneSrc = regeneratePbrtFile(self.sceneFileSrc, self.resX, self.resY, self.pixelFilter,
                                   self.sampler, self.samplesPerPixel)

        sceneDir= os.path.dirname(self._getSceneFileRelPath())

        pbrtPath = self.__getPbrtRelPath()

        extraData =          {      "pathRoot" : self.mainSceneDir,
                                    "startTask" : startTask,
                                    "endTask" : endTask,
                                    "totalTasks" : self.totalTasks,
                                    "numSubtasks" : self.numSubtasks,
                                    "num_cores" : num_cores,
                                    "outfilebasename" : self.outfilebasename,
                                    "sceneFileSrc" : sceneSrc,
                                    "sceneDir": sceneDir,
                                    "pbrtPath": pbrtPath
                                }

        hash = "{}".format(random.getrandbits(128))
        self.subTasksGiven[ hash ] = extraData
        self.subTasksGiven[ hash ][ 'status' ] = SubtaskStatus.starting
        self.subTasksGiven[ hash ][ 'perf' ] = perfIndex
        self.subTasksGiven[ hash ][ 'client_id' ] = client_id

        self._updateTaskPreview()

        return self._newComputeTaskDef(hash, extraData, workingDirectory, perfIndex)

    #######################
    def queryExtraDataForTestTask(self):

        workingDirectory = self._getWorkingDirectory()

        sceneSrc = regeneratePbrtFile(self.sceneFileSrc, 1, 1, self.pixelFilter, self.sampler,
                                   self.samplesPerPixel)

        pbrtPath = self.__getPbrtRelPath()
        sceneDir= os.path.dirname(self._getSceneFileRelPath())

        extraData =          {      "pathRoot" : self.mainSceneDir,
                                    "startTask" : 0,
                                    "endTask" : 1,
                                    "totalTasks" : self.totalTasks,
                                    "numSubtasks" : self.numSubtasks,
                                    "num_cores" : self.num_cores,
                                    "outfilebasename" : self.outfilebasename,
                                    "sceneFileSrc" : sceneSrc,
                                    "sceneDir": sceneDir,
                                    "pbrtPath": pbrtPath
                                }

        hash = "{}".format(random.getrandbits(128))

        self.testTaskResPath = getTestTaskPath(self.root_path)
        logger.debug(self.testTaskResPath)
        if not os.path.exists(self.testTaskResPath):
            os.makedirs(self.testTaskResPath)

        return self._newComputeTaskDef(hash, extraData, workingDirectory, 0)

    #######################
    def computationFinished(self, subtask_id, taskResult, dir_manager = None, resultType = 0):

        if not self.shouldAccept(subtask_id):
            return

        tmpDir = dir_manager.getTaskTemporaryDir(self.header.task_id, create = False)
        self.tmpDir = tmpDir
        trFiles = self.loadTaskResults(taskResult, resultType, tmpDir)

        if not self._verifyImgs(subtask_id, trFiles):
            self._markSubtaskFailed(subtask_id)
            self._updateTaskPreview()
            return

        if len(taskResult) > 0:
            self.subTasksGiven[ subtask_id ][ 'status' ] = SubtaskStatus.finished
            for trFile in trFiles:

                self.collectedFileNames.add(trFile)
                self.numTasksReceived += 1
                self.countingNodes[ self.subTasksGiven[ subtask_id ][ 'client_id' ] ] = 1

                self._updatePreview(trFile)
                self._updateTaskPreview()
        else:
            self._markSubtaskFailed(subtask_id)
            self._updateTaskPreview()

        if self.numTasksReceived == self.totalTasks:
            outputFileName = u"{}".format(self.outputFile, self.outputFormat)
            if self.outputFormat != "EXR":
                collector = RenderingTaskCollector()
                for file in self.collectedFileNames:
                    collector.addImgFile(file)
                collector.finalize().save(outputFileName, self.outputFormat)
                self.previewFilePath = outputFileName
            else:
                self._putCollectedFilesTogether(outputFileName, list(self.collectedFileNames), "add")

    #######################
    def restart(self):
        RenderingTask.restart(self)
        self.collectedFileNames = set()

    #######################
    def restartSubtask(self, subtask_id):
        if self.subTasksGiven[ subtask_id ][ 'status' ] == SubtaskStatus.finished:
            self.numTasksReceived += 1
        RenderingTask.restartSubtask(self, subtask_id)
        self._updateTaskPreview()

    #######################
    def getPriceMod(self, subtask_id):
        if subtask_id not in self.subTasksGiven:
            logger.error("Not my subtask {}".format(subtask_id))
            return 0
        perf =  (self.subTasksGiven[ subtask_id ]['endTask'] - self.subTasksGiven[ subtask_id ][ 'startTask' ])
        perf *= float(self.subTasksGiven[ subtask_id ]['perf']) / 1000
        return perf

    #######################
    def _getNextTask(self, perfIndex):
        if self.lastTask != self.totalTasks :
            perf = max(int(float(perfIndex) / 1500), 1)
            endTask = min(self.lastTask + perf, self.totalTasks)
            startTask = self.lastTask
            self.lastTask = endTask
            return startTask, endTask
        else:
            for sub in self.subTasksGiven.values():
                if sub['status'] == SubtaskStatus.failure:
                    sub['status'] = SubtaskStatus.resent
                    endTask = sub['endTask']
                    startTask = sub['startTask']
                    self.numFailedSubtasks -= 1
                    return startTask, endTask
        return None, None

    #######################
    def _shortExtraDataRepr(self, perfIndex, extraData):
        l = extraData
        return "pathRoot: {}, startTask: {}, endTask: {}, totalTasks: {}, numSubtasks: {}, num_cores: {}, outfilebasename: {}, sceneFileSrc: {}".format(l["pathRoot"], l["startTask"], l["endTask"], l["totalTasks"], l["numSubtasks"], l["num_cores"], l["outfilebasename"], l["sceneFileSrc"])

    #######################
    def _getPartImgSize(self, subtask_id, advTestFile):
        if advTestFile is not None:
            numTask = self.__getNumFromFileName(advTestFile[0], subtask_id)
        else:
            numTask = self.subTasksGiven[ subtask_id ][ 'startTask' ]
        numSubtask = random.randint(0, self.numSubtasks - 1)
        num = numTask * self.numSubtasks + numSubtask
        x0 = int( round((num % self.nx) * self.taskResX))
        x1 = int( round(((num % self.nx) + 1) * self.taskResX))
        y0 = int(math.floor((num / self.nx) * self.taskResY))
        y1 = int (math.floor(((num / self.nx) + 1) * self.taskResY))
        return x0, y0, x1, y1

    #######################
    def _markTaskArea(self, subtask, imgTask, color):
        for numTask in range(subtask['startTask'], subtask['endTask']):
            for sb in range(0, self.numSubtasks):
                num = self.numSubtasks * numTask + sb
                tx = num % self.nx
                ty = num /  self.nx
                xL = tx * self.taskResX
                xR = (tx + 1) * self.taskResX
                yL = ty * self.taskResY
                yR = (ty + 1) * self.taskResY

                for i in range(int(round(xL)) , int(round(xR))):
                    for j in range(int(math.floor(yL)) , int(math.floor(yR))) :
                        imgTask.putpixel((i, j), color)

    #######################
    def _changeScope(self, subtask_id, startBox, trFile):
        extraData, startBox = RenderingTask._changeScope(self, subtask_id, startBox, trFile)
        extraData[ "outfilebasename" ] = str(extraData[ "outfilebasename" ])
        extraData[ "resourcePath" ] = os.path.dirname(self.mainProgramFile)
        extraData[ "tmpPath" ] = self.tmpDir
        extraData[ "totalTasks" ] = self.totalTasks * self.numSubtasks
        extraData[ "numSubtasks" ] = 1
        extraData[ "startTask" ] = getTaskNumFromPixels(startBox[0], startBox[1], extraData[ "totalTasks" ], self.resX, self.resY, 1) - 1
        extraData[ "endTask" ] = extraData[ "startTask" ] + 1

        return extraData, startBox

    def __getPbrtRelPath(self):
        pbrtRel = os.path.relpath(os.path.dirname(self.pbrtPath), os.path.dirname(self.mainSceneFile))
        pbrtRel = os.path.join(pbrtRel, os.path.basename(self.pbrtPath))
        return pbrtRel


    #######################
    def __getNumFromFileName(self, file_, subtask_id):
        try:
            fileName = os.path.basename(file_)
            fileName, ext = os.path.splitext(fileName)
            BASENAME = "temp"
            idx = fileName.find(BASENAME)
            return int(fileName[idx + len(BASENAME):])
        except Exception, err:
            logger.error("Wrong output file name {}: {}".format(file_, str(err)))
            return self.subTasksGiven[ subtask_id ][ 'startTask' ]

#####################################################################
def getTaskNumFromPixels(pX, pY, totalTasks, resX = 300, resY = 200, subtasks = 20):
    nx, ny, taskResX, taskResY = countSubtaskReg(totalTasks, subtasks, resX, resY)
    numX = int(math.floor(pX / taskResX))
    numY = int(math.floor(pY / taskResY))
    num = (numY * nx + numX) /subtasks + 1
    return num

#####################################################################
def getTaskBoarder(startTask, endTask, totalTasks, resX = 300, resY = 200, numSubtasks = 20):
    boarder = []
    newLeft = True
    lastRight = None
    for numTask in range(startTask, endTask):
        for sb in range(numSubtasks):
            num = numSubtasks * numTask + sb
            nx, ny, taskResX, taskResY = countSubtaskReg(totalTasks, numSubtasks, resX, resY)
            tx = num % nx
            ty = num /  nx
            xL = int(round(tx * taskResX))
            xR = int (round((tx + 1) * taskResX))
            yL = int (round(ty * taskResY))
            yR = int(round((ty + 1) * taskResY))
            for i in range(xL, xR):
                if (i, yL) in boarder:
                    boarder.remove((i, yL))
                else:
                    boarder.append((i, yL))
                boarder.append((i, yR))
            if xL == 0:
                newLeft = True
            if newLeft:
                for i in range(yL, yR):
                    boarder.append((xL, i))
                newLeft = False
            if xR == resY:
                for i in range(yL, yR):
                    boarder.append((xR, i))
            lastRight = (xR, yL, yR)
    xR, yL, yR = lastRight
    for i in range(yL, yR):
        boarder.append((xR, i))
    return boarder

