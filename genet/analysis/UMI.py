from Bio import SeqIO
import pandas as pd
import numpy as np
from tqdm import tqdm


def make_df_umi(list_barcode:list, data_path:str, len_umi:int) -> pd.DataFrame:
    """ A function that separates UMIs by barcode in NGS read files 
    and creates a DataFrame summarizing the read counts.
    ---
    
    ### Args:
        list_barcode (list): List containing barcodes. pd.Series also acceptable.
        data_path (str): The path of NGS data file. FASTQ or FASTA file can be used.
        len_umi (int): The length of UMI for counting.

    ### Raises:
        ValueError: NGS data format or path error. 
        ValueError: The lengths of barcode error. Barcode length should be identical.
        ValueError: No barcode error. Check your barcode list.

    ### Returns:
        _type_: pd.DataFrame
    """    
     
    # Input checker: Check and Determine data file format
    if   data_path.split('.')[-1] in ['fastq', 'fq']: data_format = 'fastq'
    elif data_path.split('.')[-1] in ['fasta', 'fa']: data_format = 'fasta'
    else: raise ValueError('Please check your input: data_path')

    # Input checker: Check barcode length. The length of barcodes should be identical.
    list_bc_len = [len(bc) for bc in list_barcode]
    if np.std(list_bc_len) != 0: raise ValueError('Please check your input: The lengths of barcode is not identical')
    if len(list_barcode)   == 0: raise ValueError('Please check your input: No barcde found in list_barcode')
    len_bc = list_bc_len[0]
    

    # Step1: Make dictionary containing Barcodes and founded UMIs
    dict_bc = {}
    for bc in list_barcode: dict_bc[bc] = {}

    list_seq = [str(s.seq) for s in SeqIO.parse(data_path, data_format)]

    for _seq in tqdm(list_seq,
                total = len(list_seq),
                desc = 'Barcode/UMI sorting',
                ncols = 70,
                ascii = ' =',
                leave = True
                ):
        
        _bc  = _seq[:len_bc]
        _umi = _seq[len_umi:]
        
        if _bc in dict_bc: 
            if _umi in dict_bc[_bc]: dict_bc[_bc][_umi] += 1
            else                   : dict_bc[_bc][_umi] = 1
        
        else: continue

    # Step2: Make DataFrame as output
    list_df_temp = []

    for bc in tqdm(dict_bc,
                total = len(dict_bc),
                desc = 'Make output ',
                ncols = 70,
                ascii = ' =',
                leave = True
                ):
        
        list_bc  = []
        list_umi = []
        list_cnt = []
        
        for umi in dict_bc[bc]:
            list_bc.append(bc)
            list_umi.append(umi)
            list_cnt.append(dict_bc[bc][umi])
            
        df_temp = pd.DataFrame()
        df_temp['Barcode'] = list_bc
        df_temp['UMI']     = list_umi
        df_temp['count']   = list_cnt
        
        list_df_temp.append(df_temp)
        
        
    df_out = pd.concat(list_df_temp).reset_index(drop=True)

    return df_out


def count_mismatch(ref_seq:str, match_seq:str) -> int:
    ref_seq        = list(ref_seq)
    match_seq      = list(match_seq)
    mismatch_count = 0
    
    for ref, m_seq in zip(ref_seq, match_seq):
        if ref != m_seq: mismatch_count += 1
    
    return mismatch_count    


def collapse_umi(df_umi:pd.DataFrame, threshold:int=1, col_bc:str=None, col_umi:str=None, col_count:str=None,):

    list_col_names = list(df_umi.columns)

    # Default Barcode column index location = 0 (first column)
    if col_bc    == None: col_bc    = list_col_names[0]
    if col_umi   == None: col_umi   = list_col_names[1]
    if col_count == None: col_count = list_col_names[2]
    
    try   : bc_group = df_umi.groupby(by=[col_bc])
    except: raise ValueError(f'Can not find Barcode colume - {col_bc}. Please check input')
    
    try   : list_umi = df_umi[col_umi]
    except: raise ValueError(f'Can not find Barcode colume - {col_umi}. Please check input')
    
    list_bc = list(df_umi[col_bc].unique())
    list_df = []
    dict_collaped = {'Barcode':[], 'UMI':[], 'count'  :[]}
    
    for bc in tqdm(list_bc,
            total = len(list_bc),
            desc = 'Barcode collapsed',
            ncols = 70,
            ascii = ' =',
            leave = True
            ):
    # for bc in list_bc:
        df_bc = bc_group.get_group(bc)
        
        list_umi   = list(df_bc[col_umi])
        list_cnt   = list(df_bc[col_count])
        list_check = []

        for i, umi in enumerate(list_umi):
            if umi in list_check: continue
            dict_collaped[col_bc].append(bc)
            dict_collaped[col_umi].append(umi)
            dict_collaped[col_count].append(list_cnt[i])
                
            list_residual_umi = list_umi[i+1:]
            
            for _i_res, _res_umi in enumerate(list_residual_umi):
                if _res_umi in list_check: continue
                if count_mismatch(umi, _res_umi) <= threshold:
                    dict_collaped['count'][-1] += list_cnt[i+_i_res+1]
                    list_check.append(_res_umi)
                
        list_df.append(pd.DataFrame.from_dict(data=dict_collaped, orient='columns'))
    
    print('Concat output files')
    df_out = pd.concat(list_df)
        
    
    return df_out

