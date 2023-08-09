# from genet.utils import *
import genet
import genet.utils

import torch
import torch.nn.functional as F
import torch.nn as nn

import os, sys, regex, logging
import numpy as np
import pandas as pd

import tensorflow as tf
# tf.disable_v2_behavior()

from glob import glob
from Bio.SeqUtils import MeltingTemp as mt
from Bio.SeqUtils import gc_fraction as gc
from Bio.Seq import Seq
from RNA import fold_compound

np.set_printoptions(threshold=sys.maxsize)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


class DeepPrime:
    '''
    DeepPrime: pegRNA activity prediction models\n
    Input  = 121 nt DNA sequence without edit\n
    Output = 121 nt DNA sequence with edit\n
    
    ### Available Edit types\n
    sub1, sub2, sub3, ins1, ins2, ins3, del1, del2, del3\n
    
    ### Available PE systems\n
    PE2, PE2max, PE4max, NRCH_PE2, NRCH_PE2max, NRCH_PE4max\n
    
    ### Available Cell types\n
    HEK293T, HCT116, MDA-MB-231, HeLa, DLD1, A549, NIH3T3
    
    '''
    def __init__(self, sID:str, Ref_seq: str, ED_seq: str, edit_type: str, edit_len: int,
                pam:str = 'NGG', pbs_min:int = 7, pbs_max:int = 15,
                rtt_min:int = 0, rtt_max:int = 40, silence:bool = False,
                out_dir:str=os.getcwd(),
                ):
        
        # input parameters
        self.nAltIndex = 60
        self.sID, self.Ref_seq, self.ED_seq = sID, Ref_seq, ED_seq
        self.edit_type, self.edit_len, self.pam = edit_type, edit_len, pam
        self.pbs_min, self.pbs_max = pbs_min, pbs_max
        self.pbs_range = [pbs_min, pbs_max]
        self.rtt_min, self.rtt_max   = rtt_min, rtt_max
        self.silence = silence
        
        # output directory
        self.OUT_PATH = '%s/%s/'  % (out_dir, self.sID)
        self.TEMP_DIR = '%s/temp' % self.OUT_PATH
        
        # initializing
        self.set_logging()
        self.check_input()

        ## FeatureExtraction Class
        cFeat = FeatureExtraction()

        cFeat.input_id = sID
        cFeat.get_input(Ref_seq, ED_seq, edit_type, edit_len)

        cFeat.get_sAltNotation(self.nAltIndex)
        cFeat.get_all_RT_PBS(self.nAltIndex, nMinPBS= self.pbs_min-1, nMaxPBS=self.pbs_max, nMaxRT=rtt_max, pam=self.pam)
        cFeat.make_rt_pbs_combinations()
        cFeat.determine_seqs()
        cFeat.determine_secondary_structure()

        self.features = cFeat.make_output_df()
        
        del cFeat

        self.logger.info('Created an instance of DeepPrime')

    # def __init__: END


    def submit(self, pe_system:str, cell_type:str = 'HEK293T'):
        print('start pe_scre', self.Ref_seq, self.ED_seq, )

        return None

    # def submit: END


    def set_logging(self):

        self.logger = logging.getLogger(self.OUT_PATH)
        self.logger.setLevel(logging.DEBUG)

        self.formatter = logging.Formatter(
            '%(levelname)-5s @ %(asctime)s:\n\t %(message)s \n',
            datefmt='%a, %d %b %Y %H:%M:%S',
            )
        
        self.error = self.logger.error
        self.warn  = self.logger.warn
        self.debug = self.logger.debug
        self.info  = self.logger.info

        try:
            os.makedirs(self.OUT_PATH, exist_ok=True)
            os.makedirs(self.TEMP_DIR, exist_ok=True)
            self.info('Creating Folder %s' % self.OUT_PATH)
        except:
            self.error('Creating Folder failed')
            sys.exit(1)
            
        self.file_handler = logging.FileHandler('%s/log_%s.log' % (self.OUT_PATH, self.sID))
        self.file_handler.setLevel(logging.DEBUG)
        self.file_handler.setFormatter(self.formatter)
        self.logger.addHandler(self.file_handler)
        
        if self.silence != True:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setLevel(logging.DEBUG)
            self.console_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.console_handler)

        self.info('DeepPrime: pegRNA activity prediction models\n\t version: %s' % genet.__version__)


        return None

    # def set_logging: END


    def check_input(self):
        
        if self.pbs_min < 1:
            self.error('sID:%s\nPlease set PBS max length at least 1nt' % self.sID)
            raise ValueError('Please check your input: pbs_min')
        
        if self.pbs_max > 17:
            self.error('sID:%s\nPlease set PBS max length upto 17nt' % self.sID)
            raise ValueError('Please check your input: pbs_max')
        
        if self.rtt_max > 40:
            self.error('sID:%s\nPlease set RTT max length upto 40nt' % self.sID)
            raise ValueError('Please check your input: rtt_max')

        if self.edit_type not in ['sub', 'ins', 'del']:
            self.error('sID:%s\n\t Please select proper edit type.\n\t Available edit tyle: sub, ins, del' % self.sID)
            raise ValueError('Please check your input: edit_type')

        if self.edit_len > 3:
            self.error('sID:%s\n\t Please set edit length upto 3nt. Available edit length range: 1~3nt' % self.sID)
            raise ValueError('Please check your input: edit_len')
        
        if self.edit_len < 1:
            self.error('sID:%s\n\t Please set edit length at least 1nt. Available edit length range: 1~3nt' % self.sID)
            raise ValueError('Please check your input: edit_len')

        self.info('Input information\n\t ID: %s\n\t Refseq: %s\n\t EDseq :%s' % (self.sID, self.Ref_seq, self.ED_seq))

        return None
    
    # def check_input: END


    def do_something(self):
        self.logger.info('Something happened.')

        return None

    # def do_something: END
    


class FeatureExtraction:
    def __init__(self):
        self.sGuideKey = ''
        self.sChrID = ''
        self.sStrand = ''
        self.nGenomicPos = 0
        self.nEditIndex = 0
        self.nPBSLen = 0
        self.nRTTLen = 0
        self.sPBSSeq = ''
        self.sRTSeq = ''
        self.sPegRNASeq = ''
        self.sWTSeq = ''
        self.sEditedSeq = ''
        self.list_sSeqs = []
        self.type_sub = 0
        self.type_ins = 0
        self.type_del = 0
        self.fTm1 = 0.0
        self.fTm2 = 0.0
        self.fTm2new = 0.0
        self.fTm3 = 0.0
        self.fTm4 = 0.0
        self.fTmD = 0.0
        self.fMFE3 = 0.0
        self.fMFE4 = 0.0
        self.nGCcnt1 = 0
        self.nGCcnt2 = 0
        self.nGCcnt3 = 0
        self.fGCcont1 = 0.0
        self.fGCcont2 = 0.0
        self.fGCcont3 = 0.0
        self.dict_sSeqs = {}
        self.dict_sCombos = {}
        self.dict_sOutput = {}
    
    # def End: __init__
    
    def get_input(self, wt_seq, ed_seq, edit_type, edit_len):
        self.sWTSeq = wt_seq.upper()
        self.sEditedSeq = ed_seq.upper()
        self.sAltKey = edit_type + str(edit_len)
        self.sAltType = edit_type
        self.nAltLen = edit_len

        if   self.sAltType.startswith('sub'): self.type_sub = 1
        elif self.sAltType.startswith('del'): self.type_del = 1
        elif self.sAltType.startswith('ins'): self.type_ins = 1
    
    # def End: get_input

    def get_sAltNotation(self, nAltIndex):
        if self.sAltType == 'sub':
            self.sAltNotation = '%s>%s' % (
                self.sWTSeq[nAltIndex:nAltIndex + self.nAltLen], self.sEditedSeq[nAltIndex:nAltIndex + self.nAltLen])

        elif self.sAltType == 'del':
            self.sAltNotation = '%s>%s' % (
                self.sWTSeq[nAltIndex:nAltIndex + 1 + self.nAltLen], self.sEditedSeq[nAltIndex])

        else:
            self.sAltNotation = '%s>%s' % (
                self.sWTSeq[nAltIndex], self.sEditedSeq[nAltIndex:nAltIndex + self.nAltLen + 1])

    # def END: get_sAltNotation

    def get_all_RT_PBS(self, 
                    nAltIndex,
                    nMinPBS = 0,
                    nMaxPBS = 17,
                    nMaxRT = 40,
                    nSetPBSLen = 0,
                    nSetRTLen = 0,
                    pe_system = 'PE2'
                    ):
        """
        nMinPBS: If you set specific number, lower than MinPBS will be not generated. Default=0
        nMaxPBS: If you set specific number, higher than MinPBS will be not generated. Default=17
        nMaxRT = : If you set specific number, higher than MinPBS will be not generated. Default=40
        nSetPBSLen = 0  # Fix PBS Len: Set if >0
        nSetRTLen = 0  # Fix RT  Len: Set if >0
        PAM: 4-nt sequence
        """

        nMaxEditPosWin = nMaxRT + 3  # Distance between PAM and mutation

        dict_sWinSize = {'sub': {1: [nMaxRT - 1 - 3, 6], 2: [nMaxRT - 2 - 3, 6], 3: [nMaxRT - 3 - 3, 6]},
                        'ins': {1: [nMaxRT - 2 - 3, 6], 2: [nMaxRT - 3 - 3, 6], 3: [nMaxRT - 4 - 3, 6]},
                        'del': {1: [nMaxRT - 1 - 3, 6], 2: [nMaxRT - 1 - 3, 6], 3: [nMaxRT - 1 - 3, 6]}}

        
        if 'NRCH' in pe_system: # for NRCH-PE PAM
            dict_sRE = {'+': '[ACGT][ACGT]G[ACGT]|[ACGT][CG]A[ACGT]|[ACGT][AG]CC|[ATCG]ATG', 
                        '-': '[ACGT]C[ACGT][ACGT]|[ACGT]T[CG][ACGT]|G[GT]T[ACGT]|ATT[ACGT]|CAT[ACGT]|GGC[ACGT]|GTA[ACGT]'} 
        else:
            dict_sRE = {'+': '[ACGT]GG[ACGT]', '-': '[ACGT]CC[ACGT]'} # for Original-PE PAM

        for sStrand in ['+', '-']:

            sRE = dict_sRE[sStrand]
            for sReIndex in regex.finditer(sRE, self.sWTSeq, overlapped=True):

                if sStrand == '+':
                    nIndexStart = sReIndex.start()
                    nIndexEnd = sReIndex.end() - 1
                    sPAMSeq = self.sWTSeq[nIndexStart:nIndexEnd]
                    sGuideSeq = self.sWTSeq[nIndexStart - 20:nIndexEnd]
                else:
                    nIndexStart = sReIndex.start() + 1
                    nIndexEnd = sReIndex.end()
                    sPAMSeq = reverse_complement(self.sWTSeq[nIndexStart:nIndexEnd])
                    sGuideSeq = reverse_complement(self.sWTSeq[nIndexStart:nIndexEnd + 20])

                nAltPosWin = set_alt_position_window(sStrand, self.sAltKey, nAltIndex, nIndexStart, nIndexEnd,
                                                    self.nAltLen)

                ## AltPosWin Filter ##
                if nAltPosWin <= 0:             continue
                if nAltPosWin > nMaxEditPosWin: continue

                nPAM_Nick = set_PAM_nicking_pos(sStrand, self.sAltType, self.nAltLen, nAltIndex, nIndexStart, nIndexEnd)

                if not check_PAM_window(dict_sWinSize, sStrand, nIndexStart, nIndexEnd, self.sAltType, self.nAltLen,
                                        nAltIndex): continue

                sPAMKey = '%s,%s,%s,%s,%s,%s,%s' % (
                    self.sAltKey, self.sAltNotation, sStrand, nPAM_Nick, nAltPosWin, sPAMSeq, sGuideSeq)

                dict_sRT, dict_sPBS = self.determine_PBS_RT_seq(sStrand, nMinPBS, nMaxPBS, nMaxRT, nSetPBSLen,
                                                        nSetRTLen, nAltIndex, nPAM_Nick, nAltPosWin, self.sEditedSeq)

                nCnt1, nCnt2 = len(dict_sRT), len(dict_sPBS)
                if nCnt1 == 0: continue
                if nCnt2 == 0: continue
                
                if sPAMKey not in self.dict_sSeqs:
                    self.dict_sSeqs[sPAMKey] = ''
                self.dict_sSeqs[sPAMKey] = [dict_sRT, dict_sPBS]

            # loop END: sReIndex
        # loop END: sStrand


    # def END: get_all_RT_PBS

    
    def determine_PBS_RT_seq(self, sStrand, nMinPBS, nMaxPBS, nMaxRT, nSetPBSLen, nSetRTLen, nAltIndex, nPAM_Nick,
                            nAltPosWin, sForTempSeq):
        dict_sPBS = {}
        dict_sRT = {}

        list_nPBSLen = [nNo + 1 for nNo in range(nMinPBS, nMaxPBS)]
        for nPBSLen in list_nPBSLen:

            ## Set PBS Length ##
            if nSetPBSLen:
                if nPBSLen != nSetPBSLen: continue

            if sStrand == '+':
                nPBSStart = nPAM_Nick - nPBSLen  # 5' -> PamNick
                nPBSEnd = nPAM_Nick
                sPBSSeq = sForTempSeq[nPBSStart:nPBSEnd] # sForTempSeq = self.EditedSeq

            else:
                if self.sAltKey.startswith('sub'):
                    nPBSStart = nPAM_Nick
                elif self.sAltKey.startswith('ins'):
                    nPBSStart = nPAM_Nick + self.nAltLen
                elif self.sAltKey.startswith('del'):
                    nPBSStart = nPAM_Nick - self.nAltLen

                sPBSSeq = reverse_complement(sForTempSeq[nPBSStart:nPBSStart + nPBSLen]) # sForTempSeq = self.EditedSeq

            # if END: sStrand

            sKey = len(sPBSSeq)
            if sKey not in dict_sPBS:
                dict_sPBS[sKey] = ''
            dict_sPBS[sKey] = sPBSSeq
        # loop END: nPBSLen

        if sStrand == '+':
            if self.sAltKey.startswith('sub'):
                list_nRTPos = [nNo + 1 for nNo in range(nAltIndex + self.nAltLen, (nPAM_Nick + nMaxRT))] # OK
            elif self.sAltKey.startswith('ins'):
                list_nRTPos = [nNo + 1 for nNo in range(nAltIndex + self.nAltLen, (nPAM_Nick + nMaxRT))] # OK
            else:
                list_nRTPos = [nNo + 1 for nNo in range(nAltIndex, (nPAM_Nick + nMaxRT))] ## 수정! ## del2 RHA 3 del1 RHA2
        else:
            if self.sAltKey.startswith('sub'):
                list_nRTPos = [nNo for nNo in range(nPAM_Nick - 1 - nMaxRT, nAltIndex)] ## 수정! ## sub1 sub 3 RHA 0
            else:
                list_nRTPos = [nNo for nNo in range(nPAM_Nick - 3 - nMaxRT, nAltIndex + self.nAltLen - 1)] ## 수정! ## ins2 최소가 2까지 ins3 RHA 최소 3 #del2 RHA 2 del1 RHA1
        for nRTPos in list_nRTPos:

            if sStrand == '+':
                nRTStart = nPAM_Nick  # PamNick -> 3'
                nRTEnd = nRTPos
                sRTSeq = sForTempSeq[nRTStart:nRTEnd]

            else:
                if self.sAltKey.startswith('sub'):
                    nRTStart = nRTPos
                    nRTEnd = nPAM_Nick  # PamNick -> 3'
                elif self.sAltKey.startswith('ins'):
                    nRTStart = nRTPos
                    nRTEnd = nPAM_Nick + self.nAltLen  # PamNick -> 3'
                elif self.sAltKey.startswith('del'):
                    nRTStart = nRTPos
                    nRTEnd = nPAM_Nick - self.nAltLen  # PamNick -> 3'

                sRTSeq = reverse_complement(sForTempSeq[nRTStart:nRTEnd])

                if not sRTSeq: continue
            # if END: sStrand

            sKey = len(sRTSeq)

            ## Set RT Length ##
            if nSetRTLen:
                if sKey != nSetRTLen: continue

            ## Limit Max RT len ##
            if sKey > nMaxRT: continue

            ## min RT from nick site to mutation ##
            if self.sAltKey.startswith('sub'):
                if sStrand == '+':
                    if sKey < abs(nAltIndex - nPAM_Nick): continue
                else:
                    if sKey < abs(nAltIndex - nPAM_Nick + self.nAltLen - 1): continue ### 
            else:
                if sStrand == '-':
                    if sKey < abs(nAltIndex - nPAM_Nick + self.nAltLen - 1): continue

            if self.sAltKey.startswith('ins'):
                if sKey < nAltPosWin + 1: continue

            if sKey not in dict_sRT:
                dict_sRT[sKey] = ''
            dict_sRT[sKey] = sRTSeq
        # loop END: nRTPos

        return [dict_sRT, dict_sPBS]


    # def END: determine_PBS_RT_seq

    def make_rt_pbs_combinations(self):
        for sPAMKey in self.dict_sSeqs:

            dict_sRT, dict_sPBS = self.dict_sSeqs[sPAMKey]

            list_sRT = [dict_sRT[sKey] for sKey in dict_sRT]
            list_sPBS = [dict_sPBS[sKey] for sKey in dict_sPBS]

            if sPAMKey not in self.dict_sCombos:
                self.dict_sCombos[sPAMKey] = ''
            self.dict_sCombos[sPAMKey] = {'%s,%s' % (sRT, sPBS): {} for sRT in list_sRT for sPBS in list_sPBS}
        # loop END: sPAMKey


    # def END: make_rt_pbs_combinations


    def determine_seqs(self):
        for sPAMKey in self.dict_sSeqs:

            sAltKey, sAltNotation, sStrand, nPAM_Nick, nAltPosWin, sPAMSeq, sGuideSeq = sPAMKey.split(',')
            nAltPosWin = int(nAltPosWin)
            nNickIndex = int(nPAM_Nick)

            # if sStrand == '+':
            #     sWTSeq74 = self.sWTSeq[nNickIndex - 21:nNickIndex + 53]
            # else:
            #     sWTSeq74 = reverse_complement(self.sWTSeq[nNickIndex - 53:nNickIndex + 21])

            for sSeqKey in self.dict_sCombos[sPAMKey]:

                sRTSeq, sPBSSeq = sSeqKey.split(',')

                ## for Tm1
                sForTm1 = reverse_complement(sPBSSeq.replace('A', 'U'))

                if sStrand == '+':
                    ## for Tm2
                    sForTm2 = self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq)]
                    
                    ## for Tm2new
                    if self.sAltType.startswith('sub'):
                        sForTm2new = self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq)]
                    elif self.sAltType.startswith('ins'):
                        sForTm2new = self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq) - self.nAltLen]
                    else:  # del
                        sForTm2new = self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq) + self.nAltLen]

                    ## for Tm3
                    if self.sAltType.startswith('sub'):
                        sTm3antiSeq = reverse_complement(self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq)])
                    elif self.sAltType.startswith('ins'):
                        sTm3antiSeq = reverse_complement(self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq) - self.nAltLen])
                    else:  # del
                        sTm3antiSeq = reverse_complement(self.sWTSeq[nNickIndex:nNickIndex + len(sRTSeq) + self.nAltLen])                    

                else:
                    ## for Tm2
                    sForTm2 = reverse_complement(self.sWTSeq[nNickIndex - len(sRTSeq):nNickIndex])

                    ## for Tm2new
                    if self.sAltType.startswith('sub'):
                        sForTm2new = reverse_complement(self.sWTSeq[nNickIndex - len(sRTSeq):nNickIndex])
                    elif self.sAltType.startswith('ins'):
                        sForTm2new = reverse_complement(self.sWTSeq[nNickIndex - len(sRTSeq) + self.nAltLen:nNickIndex])
                    else:  # del
                        sForTm2new = reverse_complement(self.sWTSeq[nNickIndex - len(sRTSeq) - self.nAltLen:nNickIndex])

                    ## for Tm3
                    if self.sAltType.startswith('sub'):
                        sTm3antiSeq = self.sWTSeq[nNickIndex - len(sRTSeq):nNickIndex]
                    elif self.sAltType.startswith('ins'):
                        sTm3antiSeq = self.sWTSeq[nNickIndex - len(sRTSeq) + self.nAltLen:nNickIndex]
                    else:  # del
                        sTm3antiSeq = self.sWTSeq[nNickIndex - len(sRTSeq) - self.nAltLen:nNickIndex]

                # if END

                sForTm3 = [sRTSeq, sTm3antiSeq]

                ## for Tm4
                sForTm4 = [reverse_complement(sRTSeq.replace('A', 'U')), sRTSeq]


                self.dict_sCombos[sPAMKey][sSeqKey] = {'Tm1': sForTm1,
                                                        'Tm2': sForTm2,
                                                        'Tm2new': sForTm2new,
                                                        'Tm3': sForTm3,
                                                        'Tm4': sForTm4}
            # loop END: sSeqKey
        # loop END: sPAMKey
    # def END: determine_seqs


    def determine_secondary_structure(self):
        for sPAMKey in self.dict_sSeqs:

            sAltKey, sAltNotation, sStrand, nPAM_Nick, nAltPosWin, sPAMSeq, sGuideSeq = sPAMKey.split(',')
            list_sOutputKeys = ['Tm1', 'Tm2', 'Tm2new', 'Tm3', 'Tm4', 'TmD', 'nGCcnt1', 'nGCcnt2', 'nGCcnt3',
                        'fGCcont1', 'fGCcont2', 'fGCcont3', 'MFE3', 'MFE4']

            if sPAMKey not in self.dict_sOutput:
                self.dict_sOutput[sPAMKey] = {}

            for sSeqKey in self.dict_sCombos[sPAMKey]:

                if sSeqKey not in self.dict_sOutput[sPAMKey]:
                    
                    self.dict_sOutput[sPAMKey][sSeqKey] = {sKey: '' for sKey in list_sOutputKeys}

                self.determine_Tm(sPAMKey, sSeqKey)
                self.determine_GC(sPAMKey, sSeqKey)
                self.determine_MFE(sPAMKey, sSeqKey, sGuideSeq)
            # loop END: sSeqKey
        # loop END: sPAMKey


    def determine_Tm(self, sPAMKey, sSeqKey):
        sForTm1 = self.dict_sCombos[sPAMKey][sSeqKey]['Tm1']
        sForTm2 = self.dict_sCombos[sPAMKey][sSeqKey]['Tm2']
        sForTm2new = self.dict_sCombos[sPAMKey][sSeqKey]['Tm2new']
        sForTm3 = self.dict_sCombos[sPAMKey][sSeqKey]['Tm3']
        sForTm4 = self.dict_sCombos[sPAMKey][sSeqKey]['Tm4']

        ## Tm1 DNA/RNA mm1 ##
        fTm1 = mt.Tm_NN(seq=Seq(sForTm1), nn_table=mt.R_DNA_NN1)

        ## Tm2 DNA/DNA mm0 ##
        fTm2 = mt.Tm_NN(seq=Seq(sForTm2), nn_table=mt.DNA_NN3)

        ## Tm2new DNA/DNA mm0 ##
        fTm2new = mt.Tm_NN(seq=Seq(sForTm2new), nn_table=mt.DNA_NN3)

        ## Tm3 DNA/DNA mm1 ##
        if not sForTm3:
            fTm3 = 0
            fTm5 = 0

        else:
            list_fTm3 = []
            for sSeq1, sSeq2 in zip(sForTm3[0], sForTm3[1]):
                try:
                    fTm3 = mt.Tm_NN(seq=sSeq1, c_seq=sSeq2, nn_table=mt.DNA_NN3)
                except ValueError:
                    continue

                list_fTm3.append(fTm3)
            # loop END: sSeq1, sSeq2

        # if END:

        # Tm4 - revcom(AAGTcGATCC(RNA version)) + AAGTcGATCC
        fTm4 = mt.Tm_NN(seq=Seq(sForTm4[0]), nn_table=mt.R_DNA_NN1)

        # Tm5 - Tm3 - Tm2
        fTm5 = fTm3 - fTm2

        self.dict_sOutput[sPAMKey][sSeqKey]['Tm1'] = fTm1
        self.dict_sOutput[sPAMKey][sSeqKey]['Tm2'] = fTm2
        self.dict_sOutput[sPAMKey][sSeqKey]['Tm2new'] = fTm2new
        self.dict_sOutput[sPAMKey][sSeqKey]['Tm3'] = fTm3
        self.dict_sOutput[sPAMKey][sSeqKey]['Tm4'] = fTm4
        self.dict_sOutput[sPAMKey][sSeqKey]['TmD'] = fTm5

    # def END: determine_Tm


    def determine_GC(self, sPAMKey, sSeqKey):
        sRTSeqAlt, sPBSSeq = sSeqKey.split(',')

        self.nGCcnt1 = sPBSSeq.count('G') + sPBSSeq.count('C')
        self.nGCcnt2 = sRTSeqAlt.count('G') + sRTSeqAlt.count('C')
        self.nGCcnt3 = (sPBSSeq + sRTSeqAlt).count('G') + (sPBSSeq + sRTSeqAlt).count('C')
        self.fGCcont1 = 100 * gc(sPBSSeq)
        self.fGCcont2 = 100 * gc(sRTSeqAlt)
        self.fGCcont3 = 100 * gc(sPBSSeq + sRTSeqAlt)
        self.dict_sOutput[sPAMKey][sSeqKey]['nGCcnt1'] = self.nGCcnt1
        self.dict_sOutput[sPAMKey][sSeqKey]['nGCcnt2'] = self.nGCcnt2
        self.dict_sOutput[sPAMKey][sSeqKey]['nGCcnt3'] = self.nGCcnt3
        self.dict_sOutput[sPAMKey][sSeqKey]['fGCcont1'] = self.fGCcont1
        self.dict_sOutput[sPAMKey][sSeqKey]['fGCcont2'] = self.fGCcont2
        self.dict_sOutput[sPAMKey][sSeqKey]['fGCcont3'] = self.fGCcont3


    # def END: determine_GC

    def determine_MFE(self, sPAMKey, sSeqKey, sGuideSeqExt):

        sRTSeq, sPBSSeq = sSeqKey.split(',')

        ## Set GuideRNA seq ##
        sGuideSeq = 'G' + sGuideSeqExt[1:-3] ## GN19 guide seq

        # MFE_3 - RT + PBS + PolyT
        sInputSeq = reverse_complement(sPBSSeq + sRTSeq) + 'TTTTTT'
        sDBSeq, fMFE3 = fold_compound(sInputSeq).mfe()

        # MFE_4 - spacer only
        sInputSeq = sGuideSeq
        sDBSeq, fMFE4 = fold_compound(sInputSeq).mfe()

        self.dict_sOutput[sPAMKey][sSeqKey]['MFE3'] = round(fMFE3, 1)
        self.dict_sOutput[sPAMKey][sSeqKey]['MFE4'] = round(fMFE4, 1)

    # def END: determine_MFE

    def make_output_df(self):

        list_output = []
        list_sOutputKeys = ['Tm1', 'Tm2', 'Tm2new', 'Tm3', 'Tm4', 'TmD', 'nGCcnt1', 'nGCcnt2', 'nGCcnt3',
                        'fGCcont1', 'fGCcont2', 'fGCcont3', 'MFE3', 'MFE4']

        for sPAMKey in self.dict_sSeqs:

            sAltKey, sAltNotation, sStrand, nPAM_Nick, nAltPosWin, sPAMSeq, sGuideSeq = sPAMKey.split(',')
            nNickIndex = int(nPAM_Nick)

            if sStrand == '+':
                sWTSeq74 = self.sWTSeq[nNickIndex - 21:nNickIndex + 53]
                nEditPos = 61 - nNickIndex
            else:
                sWTSeq74 = reverse_complement(self.sWTSeq[nNickIndex - 53:nNickIndex + 21])
                if not self.sAltType.startswith('ins'):
                    nEditPos = nNickIndex - 60 - self.nAltLen + 1
                else:
                    nEditPos = nNickIndex - 59

            for sSeqKey in self.dict_sOutput[sPAMKey]:

                dict_seq = self.dict_sCombos[sPAMKey][sSeqKey]
                sRTTSeq, sPBSSeq = sSeqKey.split(',')
                PBSlen = len(sPBSSeq)
                RTlen = len(sRTTSeq)

                sPBS_RTSeq = sPBSSeq + sRTTSeq
                s5Bufferlen = 21 - PBSlen
                s3Bufferlen = 53 - RTlen
                sEDSeq74 = 'x' * s5Bufferlen + sPBS_RTSeq + 'x' * s3Bufferlen

                if self.sAltType.startswith('del'):
                    RHA_len = len(sRTTSeq) - nEditPos + 1
                else:
                    RHA_len = len(sRTTSeq) - nEditPos - self.nAltLen + 1


                list_sOut = [self.input_id, sWTSeq74, sEDSeq74, 
                            len(sPBSSeq), len(sRTTSeq), len(sPBSSeq + sRTTSeq), nEditPos, self.nAltLen,
                            RHA_len, self.type_sub, self.type_ins, self.type_del
                            ] + [self.dict_sOutput[sPAMKey][sSeqKey][sKey] for sKey in list_sOutputKeys]

                list_output.append(list_sOut)
            
            # loop END: sSeqKey

        hder_essen = ['ID', 'WT74_On', 'Edited74_On', 'PBSlen', 'RTlen', 'RT-PBSlen', 'Edit_pos', 'Edit_len', 'RHA_len',
                    'type_sub', 'type_ins', 'type_del','Tm1', 'Tm2', 'Tm2new', 'Tm3', 'Tm4', 'TmD',
                    'nGCcnt1', 'nGCcnt2', 'nGCcnt3', 'fGCcont1', 'fGCcont2', 'fGCcont3', 'MFE3', 'MFE4']

        df_out = pd.DataFrame(list_output, columns=hder_essen)
        
        # loop END: sPAMKey

        return df_out

# def END: make_output



class GeneInteractionModel(nn.Module):


    def __init__(self, hidden_size, num_layers, num_features=24, dropout=0.1):
        super(GeneInteractionModel, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.c1 = nn.Sequential(
            nn.Conv2d(in_channels=4, out_channels=128, kernel_size=(2, 3), stride=1, padding=(0, 1)),
            nn.BatchNorm2d(128),
            nn.GELU(),
        )
        self.c2 = nn.Sequential(
            nn.Conv1d(in_channels=128, out_channels=108, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(108),
            nn.GELU(),
            nn.AvgPool1d(kernel_size=2, stride=2),

            nn.Conv1d(in_channels=108, out_channels=108, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(108),
            nn.GELU(),
            nn.AvgPool1d(kernel_size=2, stride=2),

            nn.Conv1d(in_channels=108, out_channels=128, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(128),
            nn.GELU(),
            nn.AvgPool1d(kernel_size=2, stride=2),
        )

        self.r = nn.GRU(128, hidden_size, num_layers, batch_first=True, bidirectional=True)

        self.s = nn.Linear(2 * hidden_size, 12, bias=False)

        self.d = nn.Sequential(
            nn.Linear(num_features, 96, bias=False),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(96, 64, bias=False),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 128, bias=False)
        )

        self.head = nn.Sequential(
            nn.BatchNorm1d(140),
            nn.Dropout(dropout),
            nn.Linear(140, 1, bias=True),
        )

    def forward(self, g, x):
        g = torch.squeeze(self.c1(g), 2)
        g = self.c2(g)
        g, _ = self.r(torch.transpose(g, 1, 2))
        g = self.s(g[:, -1, :])

        x = self.d(x)

        out = self.head(torch.cat((g, x), dim=1))

        return F.softplus(out)

def seq_concat(data, col1='WT74_On', col2='Edited74_On', seq_length=74):
    wt = preprocess_seq(data[col1], seq_length)
    ed = preprocess_seq(data[col2], seq_length)
    g = np.concatenate((wt, ed), axis=1)
    g = 2 * g - 1

    return g


def select_cols(data):
    features = data.loc[:, ['PBSlen', 'RTlen', 'RT-PBSlen', 'Edit_pos', 'Edit_len', 'RHA_len', 'type_sub',
                            'type_ins', 'type_del', 'Tm1', 'Tm2', 'Tm2new', 'Tm3', 'Tm4', 'TmD',
                            'nGCcnt1', 'nGCcnt2', 'nGCcnt3', 'fGCcont1', 'fGCcont2', 'fGCcont3', 'MFE3', 'MFE4', 'DeepSpCas9_score']]

    return features



def reverse_complement(sSeq):
    dict_sBases = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N', 'U': 'U', 'n': '',
                   '.': '.', '*': '*', 'a': 't', 'c': 'g', 'g': 'c', 't': 'a'}
    list_sSeq = list(sSeq)  # Turns the sequence in to a gigantic list
    list_sSeq = [dict_sBases[sBase] for sBase in list_sSeq]
    return ''.join(list_sSeq)[::-1]

# def END: reverse_complement

def set_alt_position_window(sStrand, sAltKey, nAltIndex, nIndexStart, nIndexEnd, nAltLen):
    if sStrand == '+':

        if sAltKey.startswith('sub'):
            return (nAltIndex + 1) - (nIndexStart - 3)
        else:
            return (nAltIndex + 1) - (nIndexStart - 3)

    else:
        if sAltKey.startswith('sub'):
            return nIndexEnd - nAltIndex + 3 - (nAltLen - 1)

        elif sAltKey.startswith('del'):
            return nIndexEnd - nAltIndex + 3 - nAltLen

        else:
            return nIndexEnd - nAltIndex + 3 + nAltLen
        # if END:
    # if END:

# def END: set_alt_position_window


def set_PAM_nicking_pos(sStrand, sAltType, nAltLen, nAltIndex, nIndexStart, nIndexEnd):
    if sStrand == '-':
        nPAM_Nick = nIndexEnd + 3
    else:
        nPAM_Nick = nIndexStart - 3

    return nPAM_Nick

# def END: set_PAM_Nicking_Pos


def check_PAM_window(dict_sWinSize, sStrand, nIndexStart, nIndexEnd, sAltType, nAltLen, nAltIndex):
    nUp, nDown = dict_sWinSize[sAltType][nAltLen]

    if sStrand == '+':
        nPAMCheck_min = nAltIndex - nUp + 1
        nPAMCheck_max = nAltIndex + nDown + 1
    else:
        nPAMCheck_min = nAltIndex - nDown + 1
        nPAMCheck_max = nAltIndex + nUp + 1
    # if END:

    if nIndexStart < nPAMCheck_min or nIndexEnd > nPAMCheck_max:
        return 0
    else:
        return 1

# def END: check_PAM_window